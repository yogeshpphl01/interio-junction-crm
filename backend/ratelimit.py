"""
<module name="ratelimit" layer="security">
  <purpose>
    Per-IP anti-abuse rate limiting for the unauthenticated, cost-bearing auth &
    OTP endpoints (login, forgot/reset-password, customer request-otp/verify-otp).
    Closes the API4 "no rate limiting" gap (OWASP API Security Top 10; NIST SC-5;
    CWE-770). Complements — does not replace — the per-account lockouts already in
    place: lockout stops one account being ground down; this stops one client
    spraying many accounts or bombing the SMS/email OTP senders.
  </purpose>
  <design>
    In-memory sliding window (a deque of hit timestamps per (bucket, client-ip)).
    Process-local, which is the correct scope for the current single-backend
    deployment; the multi-instance upgrade is a shared store (Redis) behind the
    same `rate_limit()` dependency — callers don't change. Enabled by default,
    env-configurable per bucket, and **fail-open**: any internal error allows the
    request rather than locking users out on a limiter bug.
  </design>
</module>
"""
import os
import time
import logging
import threading
from collections import defaultdict, deque
from typing import Optional

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

# (bucket, client_key) -> deque[timestamps]. Guarded by _lock.
_hits: dict[tuple, deque] = defaultdict(deque)
_lock = threading.Lock()
_last_sweep = 0.0
_SWEEP_EVERY = 300  # seconds between global prunes to bound memory


def _enabled() -> bool:
    return str(os.environ.get("RATE_LIMIT_ENABLED", "1")).lower() in ("1", "true", "yes", "on")


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Behind a trusted proxy (Traefik/nginx) the real
    client is the first hop of X-Forwarded-For; otherwise the socket peer. Spoofable
    without a trusted proxy, which is acceptable for a defence-in-depth throttle."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _limit_for(bucket: str, default_max: int, default_window: int) -> tuple[int, int]:
    """Per-bucket override via env `RATE_LIMIT_<BUCKET>` = "MAX/WINDOW_SECONDS"
    (e.g. RATE_LIMIT_AUTH_LOGIN=30/300). Falls back to the coded defaults."""
    raw = os.environ.get(f"RATE_LIMIT_{bucket.upper()}")
    if raw:
        try:
            m, w = raw.split("/")
            return max(int(m), 1), max(int(w), 1)
        except (ValueError, AttributeError):
            logger.warning("ignoring malformed RATE_LIMIT_%s=%r", bucket.upper(), raw)
    return default_max, default_window


def _sweep(now: float) -> None:
    """Occasionally drop empty/stale keys so the dict can't grow without bound."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_EVERY:
        return
    _last_sweep = now
    for key in list(_hits.keys()):
        dq = _hits[key]
        # We don't know each key's window here; anything older than a day is dead.
        while dq and dq[0] < now - 86400:
            dq.popleft()
        if not dq:
            del _hits[key]


def rate_limit(bucket: str, default_max: int, default_window: int):
    """FastAPI dependency factory: allow at most `default_max` requests per
    `default_window` seconds per client IP for this `bucket`. Raises HTTP 429 with
    a Retry-After header when exceeded. No-op when disabled; fail-open on error.

    Usage:  @router.post("/auth/login", dependencies=[Depends(rate_limit("auth_login", 30, 300))])
    """
    async def _dependency(request: Request) -> None:
        if not _enabled():
            return
        try:
            limit, window = _limit_for(bucket, default_max, default_window)
            key = (bucket, _client_ip(request))
            now = time.time()
            cutoff = now - window
            with _lock:
                _sweep(now)
                dq = _hits[key]
                while dq and dq[0] < cutoff:
                    dq.popleft()
                if len(dq) >= limit:
                    retry_after = max(int(dq[0] + window - now) + 1, 1)
                    raise HTTPException(
                        status_code=429,
                        detail="Too many requests. Please slow down and try again shortly.",
                        headers={"Retry-After": str(retry_after)},
                    )
                dq.append(now)
        except HTTPException:
            raise
        except Exception as e:  # never block legitimate traffic on a limiter bug
            logger.warning("rate limiter error (failing open): %s", e)
            return

    return _dependency


def reset() -> None:
    """Clear all counters. For tests / admin reset only."""
    with _lock:
        _hits.clear()

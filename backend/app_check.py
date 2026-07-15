"""
<module name="app_check" layer="security">
  <purpose>
    App-attestation gate (Firebase App Check / Play Integrity / App Attest) for
    the unauthenticated abuse surface — customer OTP request/verify and staff
    login. Firebase App Check hands the app a short-lived RS256 JWT signed by
    Google; we verify its signature against Google's JWKS and check issuer,
    audience and expiry, so only a genuine, unmodified install of OUR apps
    (not a script or a repackaged clone) can hit those endpoints.

    OWASP MASVS-RESILIENCE / Mobile M8; NIST SC-8/SI-3; ISO A.8.26.
  </purpose>
  <safety>
    FAIL-CLOSED and opt-in. When APP_CHECK_ENABLED is off (default) the guard is
    a pass-through so today's flows are unchanged. When on, a missing/invalid/
    unverifiable token is rejected (403) — it never falls back to accepting an
    unverified token. Configure APP_CHECK_PROJECT_NUMBER (your Firebase project
    number) so audience/issuer are pinned; JWKS come from APP_CHECK_JWKS_URL
    (default Google) or can be pinned inline via APP_CHECK_JWKS_JSON.
  </safety>
</module>
"""
import os
import json
import time
import logging
import urllib.request

import jwt
from fastapi import Request, HTTPException

log = logging.getLogger("app_check")

ISSUER_BASE = "https://firebaseappcheck.googleapis.com"
DEFAULT_JWKS_URL = "https://firebaseappcheck.googleapis.com/v1/jwks"
JWKS_TTL_SEC = 3600

# RS256 needs `cryptography`. If it is missing we must fail closed when enforcing
# (never accept an unverifiable token), so record the import result here.
try:
    from jwt.algorithms import RSAAlgorithm  # noqa: F401  (requires cryptography)
    _RSA_OK = True
except Exception:  # pragma: no cover - only when cryptography is absent
    _RSA_OK = False

_jwks_cache: dict = {"keys": None, "fetched": 0.0}


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def app_check_enabled() -> bool:
    return _truthy(os.environ.get("APP_CHECK_ENABLED"))


def _project_number() -> str:
    return (os.environ.get("APP_CHECK_PROJECT_NUMBER") or "").strip()


def _load_jwks() -> dict:
    """Google's App Check public keys. `APP_CHECK_JWKS_JSON` pins them inline
    (no runtime network dependency); otherwise fetch + cache from the JWKS URL."""
    inline = os.environ.get("APP_CHECK_JWKS_JSON")
    if inline:
        return json.loads(inline)
    now = time.time()
    if _jwks_cache["keys"] is not None and (now - _jwks_cache["fetched"]) < JWKS_TTL_SEC:
        return _jwks_cache["keys"]
    url = os.environ.get("APP_CHECK_JWKS_URL", DEFAULT_JWKS_URL)
    with urllib.request.urlopen(url, timeout=5) as resp:   # nosec - trusted Google endpoint
        data = json.loads(resp.read())
    _jwks_cache["keys"] = data
    _jwks_cache["fetched"] = now
    return data


def verify_app_check_token(token: str) -> dict:
    """Verify a Firebase App Check token (RS256, Google-signed). Returns its
    claims on success; raises HTTPException(403) on any failure. Fails closed if
    the RS256 backend (`cryptography`) is unavailable."""
    if not _RSA_OK:
        log.error("APP_CHECK_ENABLED but `cryptography` is not installed — rejecting (fail-closed).")
        raise HTTPException(status_code=403, detail="App attestation unavailable")
    project = _project_number()
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=403, detail="App attestation failed")
    kid = header.get("kid")
    jwks = _load_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=403, detail="App attestation failed")
    try:
        signing_key = RSAAlgorithm.from_jwk(json.dumps(key))
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=(f"projects/{project}" if project else None),
            issuer=(f"{ISSUER_BASE}/{project}" if project else None),
            options={
                "verify_aud": bool(project),   # aud must contain projects/<number>
                "verify_iss": bool(project),   # iss must be the App Check issuer for OUR project
                "require": ["exp"],
            },
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="App attestation failed")
    return claims


async def require_app_check(request: Request) -> None:
    """FastAPI dependency. No-op unless APP_CHECK_ENABLED; then a valid
    X-Firebase-AppCheck (or X-App-Check) header is mandatory."""
    if not app_check_enabled():
        return
    token = request.headers.get("X-Firebase-AppCheck") or request.headers.get("X-App-Check")
    if not token:
        raise HTTPException(status_code=403, detail="App attestation required")
    verify_app_check_token(token)


def validate_app_check_config() -> None:
    """Called at startup: warn loudly about a misconfigured enforcement so it
    fails safe and is obvious in logs."""
    if not app_check_enabled():
        return
    if not _RSA_OK:
        log.error("APP_CHECK_ENABLED=1 but `cryptography` is missing — every attested call will 403.")
    if not _project_number():
        log.warning("APP_CHECK_ENABLED=1 but APP_CHECK_PROJECT_NUMBER is unset — audience/issuer are NOT pinned.")

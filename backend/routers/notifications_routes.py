"""
<module name="routers/notifications_routes" layer="api">
  <purpose>Admin-only email notification configuration + a rate-limited test-send.
  SMTP transport (Hostinger) lives in notifications.py.</purpose>
  <endpoints>
    GET  /api/notifications/settings -> current config (+ whether SMTP is set).
    POST /api/notifications/settings -> save master switch / recipient / per-event.
    POST /api/notifications/test     -> send a test email (5/hour/actor limit).
  </endpoints>
</module>
"""
import os
import time
from collections import deque
from fastapi import APIRouter, HTTPException, Depends
from core import (
    db, require_roles, NotificationSettingsInput, TestEmailInput, ROLE_ADMIN,
)
from audit import log_audit

router = APIRouter()

# Simple in-memory rate limit for /notifications/test:
# at most TEST_RATE_LIMIT calls per TEST_RATE_WINDOW seconds per actor.
# Survives only within a process, which is the right scope here (we don't want
# distributed coordination for an admin-only diagnostic endpoint).
TEST_RATE_LIMIT = 5
TEST_RATE_WINDOW = 3600  # 1 hour
_test_calls: dict[str, deque] = {}


def _check_test_rate(actor_id: str) -> tuple[bool, int]:
    now = time.time()
    bucket = _test_calls.setdefault(actor_id, deque())
    while bucket and bucket[0] < now - TEST_RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= TEST_RATE_LIMIT:
        retry_after = int(bucket[0] + TEST_RATE_WINDOW - now)
        return False, max(retry_after, 1)
    bucket.append(now)
    return True, 0


def _is_smtp_configured() -> bool:
    return bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USER")
        and os.environ.get("SMTP_PASSWORD")
        and os.environ.get("SENDER_EMAIL")
    )


async def _get_settings(user: dict) -> dict:
    doc = await db.settings.find_one({"key": "notifications"}, {"_id": 0})
    val = (doc or {}).get("value") or {}
    return {
        "enabled": bool(val.get("enabled", False)),
        "admin_email": val.get("admin_email") or os.environ.get("ADMIN_EMAIL"),
        "from_email": val.get("from_email") or os.environ.get("SENDER_EMAIL"),
        "events": val.get("events") or {
            "sla_breach_48h": True,
            "escalate_hot_lead": True,
            "notify_designer_revision": True,
        },
        "configured": _is_smtp_configured(),
        "provider": "smtp",
        "smtp_host": os.environ.get("SMTP_HOST"),
        "smtp_user": os.environ.get("SMTP_USER"),
    }


@router.get("/notifications/settings")
async def get_notification_settings(user: dict = Depends(require_roles(ROLE_ADMIN))):
    return await _get_settings(user)


@router.post("/notifications/settings")
async def save_notification_settings(payload: NotificationSettingsInput, user: dict = Depends(require_roles(ROLE_ADMIN))):
    value = payload.model_dump()
    await db.settings.update_one({"key": "notifications"}, {"$set": {"value": value}}, upsert=True)
    await log_audit(db, user, "notifications.settings_saved", "settings", "notifications", "Notification settings", value)
    return await _get_settings(user)


@router.post("/notifications/test")
async def send_test_notification(payload: TestEmailInput, user: dict = Depends(require_roles(ROLE_ADMIN))):
    ok_rate, retry = _check_test_rate(user["id"])
    if not ok_rate:
        raise HTTPException(
            status_code=429,
            detail=f"Test-email rate limit reached ({TEST_RATE_LIMIT}/hour). Try again in {retry}s.",
            headers={"Retry-After": str(retry)},
        )
    try:
        from notifications import send_test_email
        ok, info = await send_test_email(db, payload.to)
        return {"ok": ok, "info": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

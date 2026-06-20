"""Notification settings + test endpoints."""
import os
from fastapi import APIRouter, HTTPException, Depends
from core import (
    db, require_roles, NotificationSettingsInput, TestEmailInput, ROLE_ADMIN,
)
from audit import log_audit

router = APIRouter()


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
    try:
        from notifications import send_test_email
        ok, info = await send_test_email(db, payload.to)
        return {"ok": ok, "info": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

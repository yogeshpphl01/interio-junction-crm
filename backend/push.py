"""
<module name="push" layer="domain">
  <purpose>
    Push-notification seam for the two mobile apps (FCM-ready). It owns device
    registration and a single fire-and-forget send_push() that fans a message out
    to all of an owner's live devices. The owner is either a customer (Client App)
    or a user/employee (Company App).

    Actual delivery is stubbed — logged, not sent — until Firebase credentials are
    configured (FCM_CREDENTIALS / GOOGLE_APPLICATION_CREDENTIALS). Going live is a
    one-function change in _deliver_push(): swap the stub for
    firebase_admin.messaging.send_each_for_multicast(...). Every send is recorded
    on the audit log (notification.sent / notification.failed, channel "push") so
    the same reporting that covers email covers push.
  </purpose>
</module>
"""
import os
import uuid
import logging
from typing import Optional

from core import db, now_iso

logger = logging.getLogger(__name__)


def _fcm_configured() -> bool:
    return bool(os.environ.get("FCM_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


async def register_device(owner_type: str, owner_id: str, token: str,
                          platform: Optional[str] = None, app: Optional[str] = None) -> dict:
    """Register (or refresh, keyed on the unique token) a device for an owner."""
    ts = now_iso()
    existing = await db.device_tokens.find_one({"token": token}, {"_id": 0})
    if existing:
        await db.device_tokens.update_one({"token": token}, {"$set": {
            "owner_type": owner_type, "owner_id": owner_id,
            "platform": platform or existing.get("platform"),
            "app": app or existing.get("app"),
            "is_active": True, "last_seen_at": ts,
        }})
        return await db.device_tokens.find_one({"token": token}, {"_id": 0})
    row = {
        "id": str(uuid.uuid4()), "owner_type": owner_type, "owner_id": owner_id,
        "token": token, "platform": platform, "app": app,
        "is_active": True, "last_seen_at": ts, "created_at": ts,
    }
    await db.device_tokens.insert_one(row)
    return row


async def unregister_device(token: str) -> None:
    """Deactivate a token (logout / stale). Kept as a row for audit, not deleted."""
    await db.device_tokens.update_one({"token": token}, {"$set": {"is_active": False}})


async def devices_for(owner_type: str, owner_id: str) -> list[dict]:
    rows = await db.device_tokens.find(
        {"owner_type": owner_type, "owner_id": owner_id}, {"_id": 0}).to_list(50)
    return [r for r in rows if r.get("is_active", True)]


async def _deliver_push(tokens: list[str], title: str, body: str, data: dict) -> tuple[bool, str]:
    """
    Delivery seam. Replace the stub with firebase-admin once creds are set:

        from firebase_admin import messaging
        msg = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
        )
        resp = messaging.send_each_for_multicast(msg)
        return resp.failure_count == 0, f"sent:{resp.success_count} failed:{resp.failure_count}"
    """
    if not _fcm_configured():
        logger.info(f"[PUSH stub] -> {len(tokens)} device(s): {title} | {body} | data={data}")
        return True, f"stub:{len(tokens)}"
    logger.warning("FCM credentials present but firebase-admin delivery not wired yet")
    return False, "fcm_not_wired"


async def send_push(owner_type: str, owner_id: str, title: str, body: str,
                    data: Optional[dict] = None, lead_id: Optional[str] = None) -> None:
    """Fire-and-forget push to all of an owner's live devices. Never raises."""
    try:
        devs = await devices_for(owner_type, owner_id)
        if not devs:
            return  # no devices registered — nothing to do
        tokens = [d["token"] for d in devs]
        ok, info = await _deliver_push(tokens, title, body, data or {})
        # Deactivate tokens FCM rejected as unregistered (real impl inspects the
        # per-token response; the stub has nothing to prune).
        from audit import log_audit
        await log_audit(
            db, None, "notification.sent" if ok else "notification.failed", "push", owner_id, title,
            {"channel": "push", "owner_type": owner_type, "devices": len(tokens), "info": info, "lead_id": lead_id},
        )
    except Exception as exc:  # never break the caller because of a push
        logger.warning(f"send_push failed for {owner_type}:{owner_id}: {exc}")

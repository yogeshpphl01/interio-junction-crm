"""Audit log helper. Records every meaningful action across the CRM."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import Request

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Action vocabulary kept short + structured so the UI can filter cleanly.
ACTIONS = {
    "auth.login", "auth.login_failed", "auth.logout",
    "user.created", "user.updated",
    "lead.created", "lead.updated", "lead.stage_changed",
    "lead.closed_won", "lead.closed_lost", "lead.reopened", "lead.on_hold",
    "project.created",
    "measurement.created", "measurement.updated", "measurement.completed",
    "revision.created", "revision.updated", "revision.status_changed",
    "payment.created", "payment.updated", "payment.paid",
    "document.uploaded", "document.downloaded",
    "automation.toggled", "automation.run_checks",
    "scoring.weights_saved",
    "notification.sent", "notification.failed",
    "notifications.settings_saved",
}


async def log_audit(
    db,
    actor: Optional[dict],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_label: Optional[str] = None,
    metadata: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Fire-and-forget audit log entry. Errors are swallowed (logged)."""
    try:
        ip = None
        ua = None
        if request is not None:
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent")
        doc = {
            "id": str(uuid.uuid4()),
            "actor_id": actor["id"] if actor else None,
            "actor_email": actor["email"] if actor else None,
            "actor_name": actor["full_name"] if actor else None,
            "actor_role": actor["role"] if actor else None,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "target_label": target_label,
            "metadata": metadata or {},
            "ip": ip,
            "user_agent": ua,
            "created_at": _now(),
        }
        await db.audit_log.insert_one(doc)
    except Exception as exc:  # never break the request because of audit logging
        logger.warning(f"Audit log failed for action {action}: {exc}")

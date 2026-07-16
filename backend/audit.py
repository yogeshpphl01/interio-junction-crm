"""Audit log helper. Records every meaningful action across the CRM."""
import uuid
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import Request

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64   # prev_hash of the very first audit entry


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# <tamper-evidence> The canonical content of an entry that the hash commits to
#   (everything except the chain fields themselves). AU-9 / A.8.15. </tamper-evidence>
_HASHED_FIELDS = ("id", "actor_id", "actor_role", "action", "target_type",
                  "target_id", "target_label", "metadata", "ip", "created_at")


def entry_hash(doc: dict, prev_hash: str) -> str:
    """SHA-256 over the entry's canonical content chained to the previous hash."""
    payload = {k: doc.get(k) for k in _HASHED_FIELDS}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + "\n" + body).encode("utf-8")).hexdigest()


# Action vocabulary kept short + structured so the UI can filter cleanly.
ACTIONS = {
    "auth.login", "auth.login_failed", "auth.logout",
    "auth.password_reset_requested", "auth.password_reset_completed", "auth.password_reset_failed",
    "auth.mfa_enrolled", "auth.mfa_verified", "auth.mfa_failed", "auth.mfa_step_up", "auth.mfa_disabled",
    "auth.break_glass",   # CEO/super-account login — alert in real time (SoD Part 4)
    "user.created", "user.updated", "user.deactivated", "user.reactivated",
    "user.deleted", "user.profile_updated",
    "user.password_changed", "user.password_reset",
    "role.created", "role.updated", "role.deleted",
    "lead.created", "lead.updated", "lead.stage_changed",
    "lead.closed_won", "lead.closed_lost", "lead.reopened", "lead.on_hold",
    "project.created",
    "measurement.created", "measurement.updated", "measurement.completed",
    "revision.created", "revision.updated", "revision.status_changed",
    "payment.created", "payment.updated", "payment.paid", "payment.received",
    "payment.webhook_verified", "payment.webhook_rejected", "payment.amount_mismatch",
    "payment.refunded",
    "fixture.created", "fixture.deleted",
    "estimate.created", "estimate.submitted", "estimate.approved",
    "estimate.rejected", "estimate.shared", "estimate.accepted",
    "cutlist.ingested", "part.scanned",
    "ticket.raised", "ticket.resolved",
    "checklist.created", "checklist.completed",
    "expense.submitted", "expense.approved", "expense.rejected",
    "campaign.imported", "campaign.distributed", "leads.distributed_to_se",
    "client.otp_requested", "client.otp_failed", "client.login", "client.logout",
    "client.design_approved", "client.design_changes_requested",
    "document.uploaded", "document.downloaded",
    "automation.toggled", "automation.run_checks",
    "import.leads",
    "scoring.weights_saved",
    "notification.sent", "notification.failed",
    "notifications.settings_saved",
    # DPDP / privacy (P1-11)
    "privacy.consent_recorded", "privacy.data_exported",
    "privacy.erasure_requested", "privacy.erased", "privacy.erasure_rejected",
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
        # Tamper-evidence: chain this entry to the previous one's hash. (At this
        # scale the read-latest race is negligible; a fork still leaves every
        # entry individually verifiable against its own prev_hash.)
        prev = await db.audit_log.find({}, {"_id": 0, "hash": 1}).sort("created_at", -1).to_list(1)
        prev_hash = (prev[0].get("hash") if prev else None) or GENESIS_HASH
        doc["prev_hash"] = prev_hash
        doc["hash"] = entry_hash(doc, prev_hash)
        await db.audit_log.insert_one(doc)
    except Exception as exc:  # never break the request because of audit logging
        logger.warning(f"Audit log failed for action {action}: {exc}")


async def verify_audit_chain(db, limit: int = 100000) -> dict:
    """Walk the hash-chained audit entries oldest->newest and re-derive each hash.
    Reports the first break (a deleted or edited row). Rows written before
    hash-chaining was enabled (hash IS NULL) are skipped, so the chain is verified
    from where hashing began. Returns {ok, checked, broken_at?}."""
    rows = await db.audit_log.find({"hash": {"$ne": None}}, {"_id": 0}).sort("created_at", 1).to_list(limit)
    prev_hash = GENESIS_HASH
    for i, r in enumerate(rows):
        expected = entry_hash(r, prev_hash)
        if r.get("prev_hash") != prev_hash or r.get("hash") != expected:
            return {"ok": False, "checked": i, "broken_at": r.get("id"),
                    "at_created": r.get("created_at")}
        prev_hash = r["hash"]
    return {"ok": True, "checked": len(rows)}

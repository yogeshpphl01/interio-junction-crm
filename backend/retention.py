"""
<module name="retention" layer="domain">
  <purpose>
    DPDP storage-limitation engine (item 8 / DPDP Act §8(7)). A daily sweep that
    enforces the documented retention schedule (docs/security/DATA_RETENTION.md):

      • Enquiry-only leads (never started a project): kept 6 months from last
        engagement, then anonymized — with a 7-day advance notice first, so a
        lead is never erased unless it was notified at least NOTICE_DAYS ago
        (giving them a window to re-engage, which resets the clock).
      • Project clients: kept 10 years from delivery for warranty/legal, then
        flagged for staff review (never auto-erased — a human decides).

    De-identification reuses the same anonymizer as the erasure endpoints, so
    transactional rows (estimates/payments) are retained while PII is stripped.
  </purpose>
  <safety>
    Idempotent (guards on retention_erased_at / retention_notified_at), driven by
    absolute cutoffs so re-runs converge, and fully audited. Windows are
    overridable for tests; the scheduler is opt-in via RETENTION_SWEEP_ENABLED.
  </safety>
</module>
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from core import db, now_iso
from audit import log_audit

logger = logging.getLogger(__name__)

# Documented defaults (env-overridable for ops; args override for tests).
ENQUIRY_RETENTION_DAYS = int(os.environ.get("RETENTION_ENQUIRY_DAYS", "180"))   # 6 months
PROJECT_RETENTION_DAYS = int(os.environ.get("RETENTION_PROJECT_DAYS", "3650"))  # 10 years
NOTICE_DAYS = int(os.environ.get("RETENTION_NOTICE_DAYS", "7"))                  # advance warning
SWEEP_INTERVAL_HOURS = int(os.environ.get("RETENTION_SWEEP_INTERVAL_HOURS", "24"))


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _last_engagement(lead: dict) -> Optional[datetime]:
    """Best available 'last touched' signal for an enquiry lead."""
    return _parse(lead.get("updated_at")) or _parse(lead.get("created_at"))


async def _customer_has_project(customer_id: str) -> bool:
    """True if this customer is linked to ANY lead that has a project (→ 10-year
    basis applies; the 6-month enquiry rule must NOT touch them)."""
    if not customer_id:
        return False
    rows = await db.leads.find({"customer_id": customer_id}, {"_id": 0, "project_id": 1}).to_list(1000)
    return any(r.get("project_id") for r in rows)


async def _anonymize_lead(lead: dict) -> None:
    """De-identify a single enquiry lead in place (no linked customer account)."""
    redacted = f"erased:lead:{lead['id']}"
    await db.leads.update_one({"id": lead["id"]}, {"$set": {
        "full_name": "[erased]",
        "phone": redacted,
        "email": None,
        "retention_erased_at": now_iso(),
    }})


async def _deliver_retention_notice(lead: dict) -> None:
    """Advance-erasure notice delivery seam. Like the OTP seams, this logs in dev
    and is the single place to wire real email/SMS. The lead can re-engage (any
    update bumps updated_at) to cancel erasure."""
    who = lead.get("email") or lead.get("phone") or lead["id"]
    logger.info("[Retention] advance-erasure notice -> %s (enquiry inactive ~%dmo; will be deleted in %d days unless you re-engage)",
                who, ENQUIRY_RETENTION_DAYS // 30, NOTICE_DAYS)


async def run_retention_sweep(
    *,
    now: Optional[datetime] = None,
    enquiry_days: int = ENQUIRY_RETENTION_DAYS,
    project_days: int = PROJECT_RETENTION_DAYS,
    notice_days: int = NOTICE_DAYS,
    dry_run: bool = False,
) -> dict:
    """Run one retention pass. Returns a summary {notified, erased, review_due}.

    Order matters: notices first (so a lead that just crossed the line gets its
    warning), then erase only leads whose notice is at least `notice_days` old."""
    now = now or datetime.now(timezone.utc)
    notice_cutoff = now - timedelta(days=max(enquiry_days - notice_days, 0))  # start warning here
    erase_cutoff = now - timedelta(days=enquiry_days)                          # eligible to erase here
    notified_before = now - timedelta(days=notice_days)                       # notice must be this old
    project_cutoff = now - timedelta(days=project_days)

    summary = {"notified": 0, "erased": 0, "review_due": 0, "dry_run": dry_run}

    # Enquiry-only candidates: no project, not yet retention-erased.
    candidates = await db.leads.find(
        {"project_id": None, "retention_erased_at": None},
        {"_id": 0},
    ).to_list(5000)

    for lead in candidates:
        # A lead whose customer later did a project is a 10-year client → skip.
        if lead.get("customer_id") and await _customer_has_project(lead["customer_id"]):
            continue
        last = _last_engagement(lead)
        if not last:
            continue

        # (1) Advance notice: crossed the warning line, not notified yet.
        if lead.get("retention_notified_at") is None:
            if last < notice_cutoff:
                if not dry_run:
                    await _deliver_retention_notice(lead)
                    await db.leads.update_one({"id": lead["id"]}, {"$set": {"retention_notified_at": now_iso()}})
                    await log_audit(db, None, "retention.notice_sent", "lead", lead["id"], lead.get("full_name"),
                                    {"policy": "enquiry_6mo", "erase_in_days": notice_days})
                summary["notified"] += 1
            continue  # never notify and erase in the same pass

        # (2) Erase: past the retention window AND the notice is at least notice_days old.
        notified_at = _parse(lead.get("retention_notified_at"))
        if last < erase_cutoff and notified_at and notified_at < notified_before:
            if not dry_run:
                cid = lead.get("customer_id")
                if cid and not await _customer_has_project(cid):
                    # Cascade through the shared anonymizer (also kills the account/sessions).
                    from routers.privacy import _anonymize_customer
                    await _anonymize_customer(cid)
                    await db.leads.update_one({"id": lead["id"]}, {"$set": {"retention_erased_at": now_iso()}})
                else:
                    await _anonymize_lead(lead)
                await log_audit(db, None, "retention.erased", "lead", lead["id"], None,
                                {"policy": "enquiry_6mo", "basis": "storage_limitation"})
            summary["erased"] += 1

    # Project clients past 10 years → flag for human review (never auto-erased).
    delivered = await db.leads.find(
        {"delivered_at": {"$lt": project_cutoff.isoformat()}, "retention_erased_at": None},
        {"_id": 0, "id": 1, "project_id": 1, "delivered_at": 1},
    ).to_list(5000)
    summary["review_due"] = len(delivered)
    if delivered and not dry_run:
        await log_audit(db, None, "retention.review_due", "lead", None, None,
                        {"policy": "project_10yr", "count": len(delivered),
                         "lead_ids": [d["id"] for d in delivered][:100]})

    logger.info("[Retention] sweep done: %s", summary)
    return summary

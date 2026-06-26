"""
<module name="routers/imports" layer="api">
  <purpose>
    Bulk lead import from a manually-uploaded Excel/CSV file (the Meta
    Facebook/Instagram "Lead Ads" export format). One upload upserts many leads
    into PostgreSQL so the CRM stays in sync with ad campaigns. The pure parsing
    + column-mapping lives in meta_import.py; this file is only HTTP + DB upsert.
  </purpose>

  <endpoints>
    POST /api/imports/leads   -> upload a spreadsheet, returns an import summary.
    GET  /api/imports/batches -> recent import runs (for the UI history panel).
  </endpoints>

  <idempotency>
    Re-uploading the same file does NOT create duplicates and does NOT reset
    sales progress: leads are matched on the Meta `id` (stored as meta_lead_id,
    UNIQUE), falling back to phone. Matches only refresh contact/brief fields;
    stage, status, lifecycle_phase and journey are preserved.
  </idempotency>
</module>
"""
import uuid
import logging

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File

from core import db, get_current_user, now_iso, init_journey, ROLE_CEO, ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER
from audit import log_audit
from meta_import import parse_spreadsheet, map_meta_row

logger = logging.getLogger(__name__)
router = APIRouter()


# <constant name="_REFRESHABLE">
#   Fields an idempotent re-import is allowed to refresh on an EXISTING lead.
#   Deliberately excludes stage/status/lifecycle_phase/journey/assigned_to so the
#   sales team's hard-won progress is never overwritten by a re-upload.
# </constant>
_REFRESHABLE = (
    "full_name", "email", "phone", "city", "bhk_type", "source", "source_platform",
    "source_campaign", "scope_of_work", "project_timeline", "priority_pref",
    "is_organic", "requirements",
)


@router.post("/imports/leads")
async def import_leads(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload a Meta Lead-Ads spreadsheet and upsert its leads into the CRM."""
    if user["role"] not in (ROLE_CEO, ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/sales can import leads")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        rows = parse_spreadsheet(content, file.filename or "upload.xlsx")
    except Exception as e:
        logger.error("Failed to parse import file: %s", e)
        raise HTTPException(status_code=400, detail=f"Could not read spreadsheet: {e}")

    batch_id = str(uuid.uuid4())
    now = now_iso()
    created = updated = skipped = 0
    errors: list[dict] = []
    seen_meta: set[str] = set()

    for idx, row in enumerate(rows, start=2):  # +1 header row, +1 for 1-based
        try:
            # init_journey (from core) is injected so the journey shape is canonical.
            lead = map_meta_row(row, user["id"], batch_id, now, journey_factory=init_journey)
            if lead["full_name"] == "Unknown" and not lead["phone"] and not lead["email"]:
                skipped += 1  # nothing usable in this row
                continue
            meta_id = lead.get("meta_lead_id")
            if meta_id and meta_id in seen_meta:
                skipped += 1  # duplicate within the same file
                continue
            if meta_id:
                seen_meta.add(meta_id)

            existing = None
            if meta_id:
                existing = await db.leads.find_one({"meta_lead_id": meta_id})
            if not existing and lead["phone"]:
                existing = await db.leads.find_one({"phone": lead["phone"]})

            if existing:
                refresh = {k: lead[k] for k in _REFRESHABLE if lead.get(k) not in (None, "")}
                refresh["updated_at"] = now
                refresh["import_batch_id"] = batch_id
                if meta_id and not existing.get("meta_lead_id"):
                    refresh["meta_lead_id"] = meta_id
                await db.leads.update_one({"id": existing["id"]}, {"$set": refresh})
                updated += 1
            else:
                await db.leads.insert_one(lead)
                await db.activities.insert_one({
                    "id": str(uuid.uuid4()),
                    "lead_id": lead["id"],
                    "type": "Note",
                    "summary": f"Imported from Meta Lead Ads — {lead.get('source_campaign') or 'campaign'}.",
                    "actor_id": user["id"],
                    "created_at": now,
                })
                created += 1
        except Exception as e:  # one bad row must not abort the whole import
            logger.warning("Import row %d failed: %s", idx, e)
            errors.append({"row": idx, "reason": str(e)})

    batch = {
        "id": batch_id,
        "filename": file.filename,
        "uploaded_by": user["id"],
        "source": "meta_lead_ads",
        "total_rows": len(rows),
        "created_count": created,
        "updated_count": updated,
        "skipped_count": skipped,
        "error_count": len(errors),
        "errors": errors[:100],
        "created_at": now,
    }
    await db.import_batches.insert_one(batch)
    await log_audit(
        db, user, "import.leads", "import", batch_id, file.filename,
        {"created": created, "updated": updated, "skipped": skipped, "errors": len(errors)},
    )
    return {
        "batch_id": batch_id,
        "filename": file.filename,
        "total_rows": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:50],
    }


@router.get("/imports/batches")
async def list_import_batches(user: dict = Depends(get_current_user), limit: int = 20):
    """Recent import runs (newest first) for the Leads import-history panel."""
    if user["role"] not in (ROLE_CEO, ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await db.import_batches.find({}, {"_id": 0}).sort("created_at", -1).to_list(min(int(limit or 20), 100))

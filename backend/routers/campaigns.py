"""
<module name="routers/campaigns" layer="api">
  <purpose>
    The front of the funnel (mobile ecosystem, P0): the hierarchy lead flow
    Marketing Head -> Project Manager -> Sales Executive.
      1. MH uploads the ad-campaign Excel ('leads.upload_excel'): leads are
         imported (reusing the Meta importer) into an UNDISTRIBUTED pool tied to a
         marketing_campaigns row.
      2. MH equal-splits the campaign's leads across Project Managers
         ('leads.distribute') — round-robin.
      3. Each PM splits their leads to Sales Executives ('leads.assign'), either
         auto (random-equal round-robin) or manually.
  </purpose>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel

from core import (
    db, get_current_user, has_permission, require_permission, now_iso, init_journey,
    ROLE_MANAGER, ROLE_SALES,
)
from meta_import import parse_spreadsheet, map_meta_row
from audit import log_audit
from .imports import _REFRESHABLE   # reuse the importer's refreshable-field list

router = APIRouter()


class DistributePMIn(BaseModel):
    pm_ids: Optional[list[str]] = None            # target PMs; default = all active PMs


class DistributeSEIn(BaseModel):
    strategy: str = "auto_equal"                  # "auto_equal" | "manual"
    se_ids: Optional[list[str]] = None            # auto_equal targets; default = SEs reporting to the PM
    assignments: Optional[dict[str, str]] = None  # manual: {lead_id: se_id}


async def _active_ids(role: str, extra: Optional[dict] = None) -> list[str]:
    q = {"role": role, "is_active": True, **(extra or {})}
    return [u["id"] for u in await db.users.find(q, {"_id": 0}).to_list(1000)]


def _round_robin(lead_ids: list[str], targets: list[str]) -> dict[str, list[str]]:
    """Equal round-robin split of leads across targets. Returns target -> [lead_ids]."""
    out: dict[str, list[str]] = {t: [] for t in targets}
    for i, lid in enumerate(lead_ids):
        out[targets[i % len(targets)]].append(lid)
    return out


# -------------------------------------------------------------------- import --
@router.post("/campaigns/import")
async def import_campaign(name: str = Form(...), file: UploadFile = File(...),
                          user: dict = Depends(require_permission("leads.upload_excel"))):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        rows = parse_spreadsheet(content, file.filename or "campaign.xlsx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read spreadsheet: {e}")

    campaign_id = str(uuid.uuid4())
    now = now_iso()
    created = updated = skipped = 0
    errors: list[dict] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=2):
        try:
            lead = map_meta_row(row, user["id"], campaign_id, now, journey_factory=init_journey)
            if lead["full_name"] == "Unknown" and not lead["phone"] and not lead["email"]:
                skipped += 1
                continue
            meta_id = lead.get("meta_lead_id")
            if meta_id and meta_id in seen:
                skipped += 1
                continue
            if meta_id:
                seen.add(meta_id)
            existing = await db.leads.find_one({"meta_lead_id": meta_id}) if meta_id else None
            if not existing and lead.get("phone"):
                existing = await db.leads.find_one({"phone": lead["phone"]})
            if existing:
                refresh = {k: lead[k] for k in _REFRESHABLE if lead.get(k) not in (None, "")}
                refresh["updated_at"] = now
                refresh["campaign_id"] = campaign_id
                await db.leads.update_one({"id": existing["id"]}, {"$set": refresh})
                updated += 1
            else:
                # New campaign leads start in the UNDISTRIBUTED pool (no PM, no SE).
                lead["campaign_id"] = campaign_id
                lead["pm_id"] = None
                lead["assigned_to"] = None
                await db.leads.insert_one(lead)
                await db.activities.insert_one({
                    "id": str(uuid.uuid4()), "lead_id": lead["id"], "type": "Note",
                    "summary": f"Imported from campaign '{name}'.", "actor_id": user["id"], "created_at": now,
                })
                created += 1
        except Exception as e:
            errors.append({"row": idx, "reason": str(e)})

    await db.marketing_campaigns.insert_one({
        "id": campaign_id, "name": name, "source": "facebook", "sheet_ref": file.filename,
        "uploaded_by": user["id"], "lead_count": created, "created_at": now,
    })
    await log_audit(db, user, "campaign.imported", "campaign", campaign_id, name,
                    {"created": created, "updated": updated, "skipped": skipped})
    return {"campaign_id": campaign_id, "name": name, "total_rows": len(rows),
            "created": created, "updated": updated, "skipped": skipped, "errors": errors[:50]}


@router.get("/campaigns")
async def list_campaigns(user: dict = Depends(get_current_user)):
    if not (has_permission(user, "leads.upload_excel") or has_permission(user, "leads.distribute")
            or has_permission(user, "leads.view_all")):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await db.marketing_campaigns.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


# ------------------------------------------------------ distribute to PMs ------
@router.post("/campaigns/{campaign_id}/distribute")
async def distribute_to_pms(campaign_id: str, payload: DistributePMIn,
                            user: dict = Depends(require_permission("leads.distribute"))):
    if not await db.marketing_campaigns.find_one({"id": campaign_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Campaign not found")
    if payload.pm_ids:
        pms = []
        for pid in payload.pm_ids:
            if not await db.users.find_one({"id": pid, "role": ROLE_MANAGER, "is_active": True}):
                raise HTTPException(status_code=400, detail=f"{pid} is not an active Project Manager")
            pms.append(pid)
    else:
        pms = await _active_ids(ROLE_MANAGER)
    if not pms:
        raise HTTPException(status_code=400, detail="No active Project Managers to distribute to")

    leads = await db.leads.find({"campaign_id": campaign_id, "pm_id": None}, {"_id": 0}).to_list(100000)
    split = _round_robin([l["id"] for l in leads], pms)
    for pm, ids in split.items():
        for lid in ids:
            await db.leads.update_one({"id": lid}, {"$set": {"pm_id": pm, "updated_at": now_iso()}})
    await log_audit(db, user, "campaign.distributed", "campaign", campaign_id, None,
                    {"distributed": len(leads), "pms": len(pms)})
    return {"campaign_id": campaign_id, "distributed": len(leads),
            "project_managers": len(pms), "per_pm": {pm: len(ids) for pm, ids in split.items()}}


# ------------------------------------------------------ distribute to SEs ------
@router.post("/leads/distribute-to-se")
async def distribute_to_ses(payload: DistributeSEIn, user: dict = Depends(require_permission("leads.assign"))):
    """A Project Manager splits THEIR leads (pm_id == self) among Sales Executives."""
    if payload.strategy == "manual":
        if not payload.assignments:
            raise HTTPException(status_code=400, detail="manual strategy needs an assignments map")
        assigned = 0
        for lead_id, se_id in payload.assignments.items():
            lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
            if not lead:
                continue
            if lead.get("pm_id") != user["id"] and not has_permission(user, "leads.view_all"):
                raise HTTPException(status_code=403, detail="That lead is not assigned to you")
            if not await db.users.find_one({"id": se_id, "role": ROLE_SALES, "is_active": True}):
                raise HTTPException(status_code=400, detail=f"{se_id} is not an active Sales Executive")
            await db.leads.update_one({"id": lead_id}, {"$set": {"assigned_to": se_id, "updated_at": now_iso()}})
            assigned += 1
        await log_audit(db, user, "leads.distributed_to_se", "lead", None, None,
                        {"strategy": "manual", "assigned": assigned})
        return {"strategy": "manual", "assigned": assigned}

    # auto_equal (random-equal round-robin)
    if payload.se_ids:
        ses = []
        for sid in payload.se_ids:
            if not await db.users.find_one({"id": sid, "role": ROLE_SALES, "is_active": True}):
                raise HTTPException(status_code=400, detail=f"{sid} is not an active Sales Executive")
            ses.append(sid)
    else:
        ses = await _active_ids(ROLE_SALES, {"reports_to": user["id"]})
    if not ses:
        raise HTTPException(status_code=400, detail="No Sales Executives found (set their reports_to, or pass se_ids)")

    leads = await db.leads.find({"pm_id": user["id"], "assigned_to": None}, {"_id": 0}).to_list(100000)
    split = _round_robin([l["id"] for l in leads], ses)
    for se, ids in split.items():
        for lid in ids:
            await db.leads.update_one({"id": lid}, {"$set": {"assigned_to": se, "updated_at": now_iso()}})
    await log_audit(db, user, "leads.distributed_to_se", "lead", None, None,
                    {"strategy": "auto_equal", "assigned": len(leads), "ses": len(ses)})
    return {"strategy": "auto_equal", "assigned": len(leads),
            "sales_executives": len(ses), "per_se": {se: len(ids) for se, ids in split.items()}}

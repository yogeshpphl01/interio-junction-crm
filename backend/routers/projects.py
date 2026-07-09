"""
<module name="routers/projects" layer="api">
  <purpose>
    Employee-facing project list + detail for the Company App (mobile P0). The
    customer-facing equivalent is /client/projects; this is scoped to what the
    signed-in EMPLOYEE may see: full visibility for managers / production /
    installation roles, otherwise only their own visible projects (via the same
    visible_lead_ids rule the rest of the CRM uses). Project detail folds in the
    Infurnia production rollup so the app can paint a project in one call.
  </purpose>
</module>
"""
from fastapi import APIRouter, Depends, HTTPException

from core import db, get_current_user, has_permission, visible_lead_ids

router = APIRouter()

# Roles that see every project.
_FULL_KEYS = ("leads.view_all", "production.manage", "installation.manage")


async def _lead_brief(lead_id):
    if not lead_id:
        return None
    return await db.leads.find_one(
        {"id": lead_id}, {"_id": 0, "full_name": 1, "phone": 1, "city": 1, "stage": 1, "status": 1})


def _proj_view(p: dict, lead: dict | None) -> dict:
    return {
        "id": p["id"],
        "project_code": p.get("project_code"),
        "lead_id": p.get("lead_id"),
        "contract_value": p.get("contract_value"),
        "booking_paid": bool(p.get("booking_paid")),
        "sent_to_factory": bool(p.get("sent_to_factory")),
        "activated_at": p.get("activated_at"),
        "created_at": p.get("created_at"),
        "customer_name": (lead or {}).get("full_name"),
        "phone": (lead or {}).get("phone"),
        "city": (lead or {}).get("city"),
        "stage": (lead or {}).get("stage"),
    }


async def _visible_projects(user: dict) -> list[dict]:
    if any(has_permission(user, k) for k in _FULL_KEYS):
        return await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    ids = await visible_lead_ids(user)  # set of lead ids, or None for full visibility
    if ids is None:
        return await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    if not ids:
        return []
    return await db.projects.find(
        {"lead_id": {"$in": list(ids)}}, {"_id": 0}).sort("created_at", -1).to_list(2000)


async def _can_see(user: dict, project: dict) -> bool:
    if any(has_permission(user, k) for k in _FULL_KEYS):
        return True
    ids = await visible_lead_ids(user)
    return ids is None or project.get("lead_id") in ids


@router.get("/projects")
async def list_projects(user: dict = Depends(get_current_user)):
    rows = await _visible_projects(user)
    out = [_proj_view(p, await _lead_brief(p.get("lead_id"))) for p in rows]
    return {"projects": out}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p or not await _can_see(user, p):
        raise HTTPException(status_code=404, detail="Project not found")
    lead = await _lead_brief(p.get("lead_id"))
    parts = await db.parts.find({"project_id": project_id}, {"_id": 0, "status": 1}).to_list(20000)
    by_status: dict = {}
    for pt in parts:
        s = pt.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1
    return {**_proj_view(p, lead), "production": {"total_parts": len(parts), "by_status": by_status}}

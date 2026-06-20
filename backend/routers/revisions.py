"""
<module name="routers/revisions" layer="api">
  <purpose>2D/3D design revisions per project (the gate for moving to Quotation:
  at least one Approved revision is required by evaluate_gate).</purpose>
  <endpoints>
    POST  /api/revisions            -> create; revision_number auto-increments.
    PATCH /api/revisions/{rev_id}    -> update; designers only their own.
  </endpoints>
  <automation>Setting status to "Revision Requested" notifies the designer.</automation>
</module>
"""
import uuid
from fastapi import APIRouter, HTTPException, Depends
from core import (
    db, get_current_user, ensure_project_visible,
    RevisionInput, RevisionUpdate, run_workflow_notify_designer, now_iso,
    ROLE_ADMIN, ROLE_SALES, ROLE_DESIGNER, ROLE_SUPERVISOR,
)
from audit import log_audit

router = APIRouter()


@router.post("/revisions")
async def create_revision(payload: RevisionInput, user: dict = Depends(get_current_user)):
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_DESIGNER):
        raise HTTPException(status_code=403, detail="Forbidden")
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, payload.project_id)
    designer_id = payload.designer_id
    if user["role"] == ROLE_DESIGNER:
        designer_id = user["id"]
    last = await db.design_revisions.find({"project_id": payload.project_id}, {"revision_number": 1, "_id": 0}).sort("revision_number", -1).limit(1).to_list(1)
    next_num = (last[0]["revision_number"] + 1) if last else 1
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": payload.project_id,
        "revision_number": next_num,
        "title": payload.title,
        "designer_id": designer_id,
        "status": payload.status or "Draft",
        "client_feedback": payload.client_feedback or "",
        "created_at": now_iso(),
    }
    await db.design_revisions.insert_one(doc)
    lead = await db.leads.find_one({"project_id": payload.project_id}, {"id": 1, "_id": 0})
    if lead:
        await db.activities.insert_one({
            "id": str(uuid.uuid4()),
            "lead_id": lead["id"],
            "type": "Note",
            "summary": f"Design Revision R{next_num} created.",
            "actor_id": user["id"],
            "created_at": now_iso(),
        })
    doc.pop("_id", None)
    await log_audit(db, user, "revision.created", "revision", doc["id"], f"R{next_num} · {payload.title}", {"project_id": payload.project_id})
    return doc


@router.patch("/revisions/{rev_id}")
async def update_revision(rev_id: str, payload: RevisionUpdate, user: dict = Depends(get_current_user)):
    rev = await db.design_revisions.find_one({"id": rev_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == ROLE_SUPERVISOR:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == ROLE_DESIGNER and rev.get("designer_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your revision")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    await db.design_revisions.update_one({"id": rev_id}, {"$set": update})
    new_rev = await db.design_revisions.find_one({"id": rev_id}, {"_id": 0})
    if payload.status:
        await log_audit(db, user, "revision.status_changed", "revision", rev_id, f"R{new_rev.get('revision_number')}", {"status": payload.status})
    else:
        await log_audit(db, user, "revision.updated", "revision", rev_id, f"R{new_rev.get('revision_number')}", {"fields": list(update.keys())})
    if payload.status == "Revision Requested":
        await run_workflow_notify_designer(rev_id, new_rev)
    return new_rev

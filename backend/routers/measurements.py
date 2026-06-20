"""
<module name="routers/measurements" layer="api">
  <purpose>Site measurements per project (the gate for moving to Design: at
  least one Completed measurement is required by evaluate_gate).</purpose>
  <endpoints>
    POST  /api/measurements           -> create (admin/sales/supervisor).
    PATCH /api/measurements/{ms_id}    -> update; supervisors only their own.
    GET   /api/measurements           -> list, role-scoped + enriched with
                                          project / lead / supervisor.
  </endpoints>
</module>
"""
import uuid
from fastapi import APIRouter, HTTPException, Depends
from core import (
    db, get_current_user, ensure_project_visible, project_ids_for_designer,
    MeasurementInput, MeasurementUpdate, now_iso,
    ROLE_ADMIN, ROLE_SALES, ROLE_DESIGNER, ROLE_SUPERVISOR,
)
from audit import log_audit

router = APIRouter()


@router.post("/measurements")
async def create_measurement(payload: MeasurementInput, user: dict = Depends(get_current_user)):
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_SUPERVISOR):
        raise HTTPException(status_code=403, detail="Forbidden")
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, payload.project_id)
    supervisor_id = payload.supervisor_id
    if user["role"] == ROLE_SUPERVISOR:
        supervisor_id = user["id"]
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "supervisor_id": supervisor_id,
        "created_at": now_iso(),
    }
    await db.site_measurements.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, user, "measurement.created", "measurement", doc["id"], proj.get("project_code"), {"project_id": payload.project_id})
    return doc


@router.patch("/measurements/{ms_id}")
async def update_measurement(ms_id: str, payload: MeasurementUpdate, user: dict = Depends(get_current_user)):
    ms = await db.site_measurements.find_one({"id": ms_id}, {"_id": 0})
    if not ms:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == ROLE_SUPERVISOR and ms.get("supervisor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your measurement")
    if user["role"] in (ROLE_DESIGNER,):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    await db.site_measurements.update_one({"id": ms_id}, {"$set": update})
    new_ms = await db.site_measurements.find_one({"id": ms_id}, {"_id": 0})
    if payload.status == "Completed":
        await log_audit(db, user, "measurement.completed", "measurement", ms_id, None, {"area": new_ms.get("total_area_sqft")})
    else:
        await log_audit(db, user, "measurement.updated", "measurement", ms_id, None, {"fields": list(update.keys())})
    return new_ms


@router.get("/measurements")
async def list_measurements(user: dict = Depends(get_current_user)):
    filt: dict = {}
    if user["role"] == ROLE_SUPERVISOR:
        filt["supervisor_id"] = user["id"]
    elif user["role"] == ROLE_DESIGNER:
        pids = await project_ids_for_designer(user["id"])
        filt["project_id"] = {"$in": pids}
    elif user["role"] == ROLE_SALES:
        lead_docs = await db.leads.find({"assigned_to": user["id"], "project_id": {"$ne": None}}, {"project_id": 1, "_id": 0}).to_list(5000)
        filt["project_id"] = {"$in": [l["project_id"] for l in lead_docs]}
    measurements = await db.site_measurements.find(filt, {"_id": 0}).sort("scheduled_at", -1).to_list(1000)
    proj_ids = list({m["project_id"] for m in measurements})
    sup_ids = list({m.get("supervisor_id") for m in measurements if m.get("supervisor_id")})
    projs = {p["id"]: p async for p in db.projects.find({"id": {"$in": proj_ids}}, {"_id": 0})}
    lead_ids = [p["lead_id"] for p in projs.values()]
    leads = {l["id"]: l async for l in db.leads.find({"id": {"$in": lead_ids}}, {"_id": 0})}
    sups = {u["id"]: u async for u in db.users.find({"id": {"$in": sup_ids}}, {"_id": 0, "password_hash": 0})}
    for m in measurements:
        p = projs.get(m["project_id"])
        m["project"] = p
        m["lead"] = leads.get(p["lead_id"]) if p else None
        m["supervisor"] = sups.get(m.get("supervisor_id"))
    return measurements

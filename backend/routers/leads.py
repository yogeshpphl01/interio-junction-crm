"""Leads (Kanban cards): CRUD + stage move + close (Won/Lost/Hold)."""
import uuid
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from core import (
    db, get_current_user, ensure_lead_visible, enrich_leads, visible_lead_ids,
    next_project_code, evaluate_gate, run_workflow_auto_assign_supervisor,
    LeadCreate, LeadUpdate, StageMoveInput, CloseLeadInput, now_iso,
    STAGES, LEAD_TYPES, BHK_TYPES, KITCHEN_LAYOUTS, LEAD_SOURCES,
    ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER,
    # <journey-helpers>maintain lifecycle_phase / furthest_stage / journey</journey-helpers>
    derive_lifecycle_phase, init_journey, record_stage_transition,
    close_open_journey_entry, JOURNEY_DELIVERED_STAGE,
)
from audit import log_audit

router = APIRouter()


@router.get("/leads")
async def list_leads(
    user: dict = Depends(get_current_user),
    stage: Optional[int] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
):
    filt: dict = {}
    if user["role"] in (ROLE_ADMIN, ROLE_MANAGER):
        pass
    elif user["role"] == ROLE_SALES:
        filt["assigned_to"] = user["id"]
    else:
        ids = await visible_lead_ids(user)
        filt["id"] = {"$in": list(ids or [])}
    if stage is not None:
        filt["stage"] = stage
    if status:
        filt["status"] = status
    # <search>Server-side search across Name / City / phone / email / Client ID
    #   (Client ID = the project code, resolved via the projects table).</search>
    if q and q.strip():
        term = q.strip()
        or_clauses = [{f: {"$regex": term, "$options": "i"}}
                      for f in ("full_name", "city", "phone", "email", "meta_lead_id")]
        proj_rows = await db.projects.find({"project_code": {"$regex": term, "$options": "i"}}, {"id": 1, "_id": 0}).to_list(500)
        if proj_rows:
            or_clauses.append({"project_id": {"$in": [p["id"] for p in proj_rows]}})
        filt["$or"] = or_clauses
    leads = await db.leads.find(filt, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    return await enrich_leads(leads)


@router.post("/leads")
async def create_lead(payload: LeadCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/sales can create leads")
    if payload.lead_type not in LEAD_TYPES:
        raise HTTPException(status_code=400, detail="Invalid lead_type")
    if payload.bhk_type not in BHK_TYPES:
        raise HTTPException(status_code=400, detail="Invalid bhk_type")
    if payload.kitchen_layout not in KITCHEN_LAYOUTS:
        raise HTTPException(status_code=400, detail="Invalid kitchen_layout")
    if payload.source not in LEAD_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    assigned = payload.assigned_to or user["id"]
    ts = now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "assigned_to": assigned,
        "created_by": user["id"],
        "stage": 1,
        "status": "Active",
        "project_id": None,
        # <journey-init>A new lead has only enquired so far (stage 1).</journey-init>
        "lifecycle_phase": "Enquiry",
        "furthest_stage": 1,
        "journey": init_journey(ts),
        "created_at": ts,
        "updated_at": ts,
    }
    await db.leads.insert_one(doc)
    doc.pop("_id", None)
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": doc["id"],
        "type": "Note",
        "summary": f"Lead created from {payload.source}.",
        "actor_id": user["id"],
        "created_at": now_iso(),
    })
    await log_audit(db, user, "lead.created", "lead", doc["id"], doc["full_name"],
                    {"source": payload.source, "budget": payload.tentative_budget})
    return (await enrich_leads([doc]))[0]


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    enriched = (await enrich_leads([lead]))[0]
    project = enriched.get("project")
    measurements, revisions, payments, documents = [], [], [], []
    if project:
        measurements = await db.site_measurements.find({"project_id": project["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
        revisions = await db.design_revisions.find({"project_id": project["id"]}, {"_id": 0}).sort("revision_number", 1).to_list(500)
        payments = await db.payments.find({"project_id": project["id"]}, {"_id": 0}).sort("due_date", 1).to_list(500)
        documents = await db.documents.find({"project_id": project["id"], "is_deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    activities = await db.activities.find({"lead_id": lead_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    stage_history = await db.stage_history.find({"lead_id": lead_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    actor_ids = {a.get("actor_id") for a in activities} | {h.get("changed_by") for h in stage_history}
    actor_ids.discard(None)
    actors = {u["id"]: u async for u in db.users.find({"id": {"$in": list(actor_ids)}}, {"_id": 0, "password_hash": 0})}
    # Batch-load any designer / supervisor IDs missing from the actors map
    missing_user_ids = {r.get("designer_id") for r in revisions if r.get("designer_id") and r.get("designer_id") not in actors}
    missing_user_ids |= {m.get("supervisor_id") for m in measurements if m.get("supervisor_id") and m.get("supervisor_id") not in actors}
    missing_user_ids.discard(None)
    if missing_user_ids:
        extras = {u["id"]: u async for u in db.users.find({"id": {"$in": list(missing_user_ids)}}, {"_id": 0, "password_hash": 0})}
        actors.update(extras)
    for a in activities:
        a["actor"] = actors.get(a.get("actor_id"))
    for h in stage_history:
        h["actor"] = actors.get(h.get("changed_by"))
    for r in revisions:
        r["designer"] = actors.get(r.get("designer_id"))
    for m in measurements:
        m["supervisor"] = actors.get(m.get("supervisor_id"))
    return {
        **enriched, "measurements": measurements, "revisions": revisions,
        "payments": payments, "documents": documents,
        "activities": activities, "stage_history": stage_history,
    }


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/sales can edit leads")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    update["updated_at"] = now_iso()
    await db.leads.update_one({"id": lead_id}, {"$set": update})
    new_lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    await log_audit(db, user, "lead.updated", "lead", lead_id, new_lead.get("full_name"), {"fields": list(update.keys())})
    return (await enrich_leads([new_lead]))[0]


@router.post("/leads/{lead_id}/close")
async def close_lead(lead_id: str, payload: CloseLeadInput, request: Request, user: dict = Depends(get_current_user)):
    """Mark a lead as Won / Lost / On-hold (or reopen to Active) with a reason."""
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/sales can close leads")
    if payload.status == "Lost" and not (payload.reason and payload.reason.strip()):
        raise HTTPException(status_code=400, detail="Lost reason is required")

    ts = now_iso()
    update: dict[str, Any] = {"status": payload.status, "updated_at": ts}
    # <journey-on-close>
    #   Closing a lead also resolves its journey: Won/factory => Completed,
    #   Lost => Dropped (we remember the stage + reason they dropped at),
    #   On-hold => paused, Active => reopened (clear drop-off markers).
    # </journey-on-close>
    if payload.status == "Lost":
        update["lost_reason"] = payload.reason.strip()
        update["closed_at"] = ts
        update["lifecycle_phase"] = "Dropped"
        update["dropped_stage"] = int(lead.get("furthest_stage") or lead.get("stage") or 1)
        update["dropped_at"] = ts
        update["dropped_reason"] = payload.reason.strip()
        update["journey"] = close_open_journey_entry(lead.get("journey"), ts)
    elif payload.status == "Won":
        update["won_reason"] = (payload.reason or "").strip() or None
        update["closed_at"] = ts
        update["lifecycle_phase"] = "Completed"
        update["journey"] = close_open_journey_entry(lead.get("journey"), ts)
        if payload.won_value is not None:
            update["won_value"] = float(payload.won_value)
            if lead.get("project_id"):
                await db.projects.update_one(
                    {"id": lead["project_id"]},
                    {"$set": {"contract_value": float(payload.won_value), "signed_off": True}},
                )
    elif payload.status == "On-hold":
        update["hold_reason"] = (payload.reason or "").strip() or None
        update["lifecycle_phase"] = "On-hold"
    elif payload.status == "Active":
        update["lost_reason"] = None
        update["won_reason"] = None
        update["hold_reason"] = None
        update["closed_at"] = None
        # Reopening: recompute the bucket from the current stage, clear drop-off.
        update["lifecycle_phase"] = derive_lifecycle_phase(int(lead.get("stage") or 1), "Active")
        update["dropped_stage"] = None
        update["dropped_at"] = None
        update["dropped_reason"] = None

    await db.leads.update_one({"id": lead_id}, {"$set": update})

    summary_map = {
        "Won": f"Marked Won. {payload.reason or ''}".strip(),
        "Lost": f"Marked Lost — {payload.reason}",
        "On-hold": f"Put on hold. {payload.reason or ''}".strip(),
        "Active": "Reopened.",
    }
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "type": "Note",
        "summary": summary_map[payload.status],
        "actor_id": user["id"],
        "created_at": now_iso(),
    })

    audit_action = {
        "Won": "lead.closed_won",
        "Lost": "lead.closed_lost",
        "On-hold": "lead.on_hold",
        "Active": "lead.reopened",
    }[payload.status]
    await log_audit(
        db, user, audit_action, "lead", lead_id, lead.get("full_name"),
        {"reason": payload.reason, "won_value": payload.won_value}, request,
    )

    new_lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    return (await enrich_leads([new_lead]))[0]


@router.post("/leads/{lead_id}/move")
async def move_lead(lead_id: str, payload: StageMoveInput, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(status_code=403, detail="Only admin/sales can move leads")
    await ensure_lead_visible(user, lead)
    to = int(payload.to_stage)
    if to < 1 or to > 6:
        raise HTTPException(status_code=400, detail="Invalid stage")
    if to == lead["stage"]:
        return (await enrich_leads([lead]))[0]
    allowed, reason = await evaluate_gate(lead, to)
    if not allowed and not (payload.override and user["role"] == ROLE_ADMIN):
        raise HTTPException(status_code=409, detail=reason)

    from_stage = lead["stage"]
    ts = now_iso()
    update: dict[str, Any] = {"stage": to, "updated_at": ts}

    # <journey-tracking>
    #   Record the stage transition, bump the furthest stage ever reached, and
    #   recompute the high-level lifecycle bucket. Stamp delivery time when the
    #   lead reaches the factory stage (the end of the journey).
    # </journey-tracking>
    update["journey"] = record_stage_transition(lead.get("journey"), to, ts)
    update["furthest_stage"] = max(int(lead.get("furthest_stage") or lead.get("stage") or 1), to)
    update["lifecycle_phase"] = derive_lifecycle_phase(to, lead.get("status", "Active"))
    if to >= JOURNEY_DELIVERED_STAGE and not lead.get("delivered_at"):
        update["delivered_at"] = ts

    if to >= 3 and not lead.get("project_id"):
        code = await next_project_code()
        proj_doc = {
            "id": str(uuid.uuid4()),
            "project_code": code,
            "lead_id": lead_id,
            "rough_estimate": lead.get("tentative_budget", 0),
            "contract_value": None,
            "signed_off": False,
            "sent_to_factory": False,
            "factory_handover_at": None,
            "created_at": now_iso(),
        }
        await db.projects.insert_one(proj_doc)
        update["project_id"] = proj_doc["id"]
        await log_audit(db, user, "project.created", "project", proj_doc["id"], proj_doc["project_code"], {"lead_id": lead_id})
        await run_workflow_auto_assign_supervisor(lead_id, proj_doc["id"])

    if to >= 5 and from_stage < 5 and lead.get("project_id"):
        await db.projects.update_one({"id": lead["project_id"]}, {"$set": {"signed_off": True, "contract_value": lead.get("tentative_budget")}})
    if to >= 6 and from_stage < 6 and lead.get("project_id"):
        await db.projects.update_one({"id": lead["project_id"]}, {"$set": {"sent_to_factory": True, "factory_handover_at": now_iso()}})

    await db.leads.update_one({"id": lead_id}, {"$set": update})

    await db.stage_history.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "from_stage": from_stage,
        "to_stage": to,
        "changed_by": user["id"],
        "note": payload.note or "",
        "created_at": now_iso(),
    })
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "type": "Stage Change",
        "summary": f"Moved from {STAGES[from_stage-1]['short']} → {STAGES[to-1]['short']}.",
        "actor_id": user["id"],
        "created_at": now_iso(),
    })
    await log_audit(
        db, user, "lead.stage_changed", "lead", lead_id, lead.get("full_name"),
        {"from": from_stage, "to": to, "override": bool(payload.override and not allowed)},
    )
    new_lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    return (await enrich_leads([new_lead]))[0]


@router.post("/leads/{lead_id}/check-gate")
async def check_gate(lead_id: str, payload: StageMoveInput, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    allowed, reason = await evaluate_gate(lead, int(payload.to_stage))
    return {"allowed": allowed, "reason": reason}

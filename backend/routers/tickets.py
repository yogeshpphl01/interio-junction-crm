"""
<module name="routers/tickets" layer="api">
  <purpose>
    Site/production tickets (mobile ecosystem, P0). The Site Manager raises a
    damaged / missing / fitting issue (with photos) against a project — and, when
    known, a specific Infurnia part — and the Production Engineer resolves it,
    optionally sending the part back into production (status -> rework). Both the
    raise and resolve actions need the 'tickets.manage' permission (SM & PE).
    Reads are open to ticket managers or anyone who can see the project.
  </purpose>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, get_current_user, has_permission, require_permission, ensure_project_visible, now_iso
from audit import log_audit

router = APIRouter()

KINDS = {"damaged", "missing", "fitting"}
PRIORITIES = {"low", "normal", "high", "urgent"}


class MediaIn(BaseModel):
    kind: Optional[str] = "image"      # image / video
    storage_ref: str


class TicketIn(BaseModel):
    project_id: str
    kind: str
    title: str
    priority: Optional[str] = "normal"
    description: Optional[str] = None
    part_uid: Optional[str] = None
    assigned_to: Optional[str] = None  # Production Engineer user id (optional)
    media: list[MediaIn] = []


class ResolveIn(BaseModel):
    note: Optional[str] = None
    remanufacture: bool = False        # if true and a part is linked, send it back to production


async def _read_guard(user: dict, project_id: str) -> None:
    if has_permission(user, "tickets.manage"):
        return
    await ensure_project_visible(user, project_id)


async def _with_media(t: dict) -> dict:
    t["media"] = await db.ticket_media.find({"ticket_id": t["id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return t


@router.post("/tickets")
async def raise_ticket(payload: TicketIn, user: dict = Depends(require_permission("tickets.manage"))):
    if payload.kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(KINDS)}")
    if (payload.priority or "normal") not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of {sorted(PRIORITIES)}")
    if not await db.projects.find_one({"id": payload.project_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Project not found")
    ts = now_iso()
    # Auto-assign to a Production Engineer if none supplied.
    assigned = payload.assigned_to
    if not assigned:
        pe = await db.users.find_one({"role": "production_engineer", "is_active": True}, {"_id": 0, "id": 1})
        assigned = pe["id"] if pe else None
    ticket = {
        "id": str(uuid.uuid4()),
        "project_id": payload.project_id,
        "part_uid": payload.part_uid,
        "kind": payload.kind,
        "priority": payload.priority or "normal",
        "status": "open",
        "title": payload.title.strip(),
        "description": payload.description,
        "raised_by": user["id"],
        "assigned_to": assigned,
        "created_at": ts,
        "resolved_at": None,
    }
    await db.tickets.insert_one(ticket)
    for m in payload.media:
        await db.ticket_media.insert_one({
            "id": str(uuid.uuid4()), "ticket_id": ticket["id"], "kind": m.kind or "image",
            "storage_ref": m.storage_ref, "uploaded_by": user["id"], "created_at": ts,
        })
    ticket.pop("_id", None)
    await log_audit(db, user, "ticket.raised", "ticket", ticket["id"], ticket["title"],
                    {"project_id": payload.project_id, "kind": payload.kind, "part_uid": payload.part_uid})
    return await _with_media(ticket)


@router.get("/tickets")
async def list_tickets(user: dict = Depends(get_current_user), project_id: Optional[str] = None,
                       status: Optional[str] = None, assigned_to: Optional[str] = None):
    filt: dict = {}
    if project_id:
        await _read_guard(user, project_id)
        filt["project_id"] = project_id
    elif not has_permission(user, "tickets.manage"):
        raise HTTPException(status_code=400, detail="project_id is required")
    if status:
        filt["status"] = status
    if assigned_to:
        filt["assigned_to"] = assigned_to
    return await db.tickets.find(filt, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, user: dict = Depends(get_current_user)):
    t = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await _read_guard(user, t["project_id"])
    return await _with_media(t)


@router.post("/tickets/{ticket_id}/media")
async def add_media(ticket_id: str, payload: MediaIn, user: dict = Depends(require_permission("tickets.manage"))):
    t = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    doc = {"id": str(uuid.uuid4()), "ticket_id": ticket_id, "kind": payload.kind or "image",
           "storage_ref": payload.storage_ref, "uploaded_by": user["id"], "created_at": now_iso()}
    await db.ticket_media.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: str, payload: ResolveIn, user: dict = Depends(require_permission("tickets.manage"))):
    t = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if t["status"] == "resolved":
        raise HTTPException(status_code=409, detail="Ticket already resolved")
    ts = now_iso()
    await db.tickets.update_one({"id": ticket_id}, {"$set": {"status": "resolved", "resolved_at": ts}})
    # Optionally send the linked part back into production (re-cut in Infurnia -> re-ingest).
    if payload.remanufacture and t.get("part_uid"):
        await db.parts.update_one({"part_uid": t["part_uid"]},
                                  {"$set": {"status": "rework", "current_station": None, "updated_at": ts}})
    await log_audit(db, user, "ticket.resolved", "ticket", ticket_id, t.get("title"),
                    {"remanufacture": payload.remanufacture, "part_uid": t.get("part_uid")})
    return await _with_media(await db.tickets.find_one({"id": ticket_id}, {"_id": 0}))

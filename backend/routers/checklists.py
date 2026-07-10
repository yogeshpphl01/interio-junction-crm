"""
<module name="routers/checklists" layer="api">
  <purpose>
    Digital checklists (mobile ecosystem, P0): factory / pack / load / unload /
    install / closure — each item can carry a photo and the checklist is signed
    off (e-signature ref). Managing checklists needs 'production.manage' (PE, for
    factory/pack) or 'installation.manage' (SM, for site checklists).

    The headline is the **load/unload reconciliation** (§14/§18): it closes the
    physical loop by comparing what was scanned "loaded/dispatched" against what
    was scanned "unloaded" on site — instantly surfacing missing / short-shipped
    Infurnia parts so the Site Manager can raise a ticket.
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

TYPES = {"factory", "pack", "load", "unload", "install", "closure"}


class ChecklistIn(BaseModel):
    project_id: str
    type: str
    items: list[str] = []          # initial item labels


class ItemUpdateIn(BaseModel):
    checked: Optional[bool] = None
    photo_ref: Optional[str] = None
    note: Optional[str] = None


class CompleteIn(BaseModel):
    signature_ref: Optional[str] = None


def _can_manage(user: dict) -> bool:
    return has_permission(user, "production.manage") or has_permission(user, "installation.manage")


async def _read_guard(user: dict, project_id: str) -> None:
    if _can_manage(user):
        return
    await ensure_project_visible(user, project_id)


def _require_manage(user: dict) -> None:
    if not _can_manage(user):
        raise HTTPException(status_code=403, detail="Forbidden: needs production.manage or installation.manage")


async def _with_items(c: dict) -> dict:
    c["items"] = await db.checklist_items.find({"checklist_id": c["id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return c


@router.post("/checklists")
async def create_checklist(payload: ChecklistIn, user: dict = Depends(get_current_user)):
    _require_manage(user)
    if payload.type not in TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(TYPES)}")
    if not await db.projects.find_one({"id": payload.project_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Project not found")
    ts = now_iso()
    checklist = {
        "id": str(uuid.uuid4()), "project_id": payload.project_id, "type": payload.type,
        "status": "open", "signed_by": None, "signature_ref": None,
        "created_at": ts, "completed_at": None,
    }
    await db.checklists.insert_one(checklist)
    for label in payload.items:
        if label and label.strip():
            await db.checklist_items.insert_one({
                "id": str(uuid.uuid4()), "checklist_id": checklist["id"], "label": label.strip(),
                "checked": False, "photo_ref": None, "note": None,
                "checked_by": None, "checked_at": None,
            })
    checklist.pop("_id", None)
    await log_audit(db, user, "checklist.created", "checklist", checklist["id"], payload.type,
                    {"project_id": payload.project_id, "items": len(payload.items)})
    return await _with_items(checklist)


@router.get("/checklists")
async def list_checklists(user: dict = Depends(get_current_user), project_id: str = None, type: Optional[str] = None):
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    await _read_guard(user, project_id)
    filt: dict = {"project_id": project_id}
    if type:
        filt["type"] = type
    return await db.checklists.find(filt, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/checklists/{checklist_id}")
async def get_checklist(checklist_id: str, user: dict = Depends(get_current_user)):
    c = await db.checklists.find_one({"id": checklist_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Checklist not found")
    await _read_guard(user, c["project_id"])
    return await _with_items(c)


@router.post("/checklists/{checklist_id}/items")
async def add_item(checklist_id: str, label: str, user: dict = Depends(get_current_user)):
    _require_manage(user)
    c = await db.checklists.find_one({"id": checklist_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Checklist not found")
    item = {"id": str(uuid.uuid4()), "checklist_id": checklist_id, "label": label.strip(),
            "checked": False, "photo_ref": None, "note": None, "checked_by": None, "checked_at": None}
    await db.checklist_items.insert_one(item)
    item.pop("_id", None)
    return item


@router.patch("/checklists/{checklist_id}/items/{item_id}")
async def update_item(checklist_id: str, item_id: str, payload: ItemUpdateIn, user: dict = Depends(get_current_user)):
    _require_manage(user)
    item = await db.checklist_items.find_one({"id": item_id, "checklist_id": checklist_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    update: dict = {}
    if payload.checked is not None:
        update["checked"] = payload.checked
        update["checked_by"] = user["id"] if payload.checked else None
        update["checked_at"] = now_iso() if payload.checked else None
    if payload.photo_ref is not None:
        update["photo_ref"] = payload.photo_ref
    if payload.note is not None:
        update["note"] = payload.note
    if update:
        await db.checklist_items.update_one({"id": item_id}, {"$set": update})
    return await db.checklist_items.find_one({"id": item_id}, {"_id": 0})


@router.post("/checklists/{checklist_id}/complete")
async def complete_checklist(checklist_id: str, payload: CompleteIn, user: dict = Depends(get_current_user)):
    _require_manage(user)
    c = await db.checklists.find_one({"id": checklist_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Checklist not found")
    items = await db.checklist_items.find({"checklist_id": checklist_id}, {"_id": 0}).to_list(500)
    unchecked = [i for i in items if not i.get("checked")]
    if unchecked:
        raise HTTPException(status_code=400, detail=f"{len(unchecked)} item(s) still unchecked")
    await db.checklists.update_one({"id": checklist_id}, {"$set": {
        "status": "completed", "signed_by": user["id"],
        "signature_ref": payload.signature_ref, "completed_at": now_iso(),
    }})
    await log_audit(db, user, "checklist.completed", "checklist", checklist_id, c["type"], {"project_id": c["project_id"]})
    return await _with_items(await db.checklists.find_one({"id": checklist_id}, {"_id": 0}))


# ---------------------------------------------------------------------------
# The physical loop: load/unload reconciliation against the Infurnia QR scans.
# ---------------------------------------------------------------------------
_LOADED = {"loaded", "dispatched", "unloaded", "installed"}   # reached loading or beyond
_UNLOADED = {"unloaded", "installed"}                          # confirmed on-site


@router.get("/projects/{project_id}/loading-reconciliation")
async def loading_reconciliation(project_id: str, user: dict = Depends(get_current_user)):
    """Compare parts that were loaded/dispatched against those unloaded on site.
    Parts loaded but not yet unloaded are the missing / short-shipped panels —
    the Site Manager raises a ticket for them."""
    await _read_guard(user, project_id)
    parts = await db.parts.find({"project_id": project_id}, {"_id": 0}).to_list(20000)
    loaded = [p for p in parts if p.get("status") in _LOADED]
    unloaded = [p for p in parts if p.get("status") in _UNLOADED]
    missing = [
        {"part_uid": p["part_uid"], "name": p.get("name"), "status": p.get("status")}
        for p in parts if p.get("status") in ("loaded", "dispatched")   # loaded but not yet unloaded
    ]
    return {
        "project_id": project_id,
        "total_parts": len(parts),
        "loaded_count": len(loaded),
        "unloaded_count": len(unloaded),
        "missing_count": len(missing),
        "reconciled": len(missing) == 0 and len(loaded) > 0,
        "missing_parts": missing,
    }

"""
<module name="routers/roles" layer="api">
  <purpose>
    Module 7 — manage account categories (roles). Anyone signed in can READ the
    role list + permission catalog (needed for dropdowns/badges). Creating,
    editing and soft-deleting categories requires the 'roles.manage' permission
    (CEO/Admin by default). Built-in roles cannot be deleted; deleting a custom
    category soft-deletes it (the record is retained in the database).
  </purpose>
</module>
"""
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, get_current_user, now_iso
from permissions import require_permission, refresh_role_cache, PERMISSION_CATALOG, ALL_PERMISSIONS
from audit import log_audit

router = APIRouter()


class RoleInput(BaseModel):
    label: str
    color: Optional[str] = "#8A817C"
    permissions: list[str] = []
    base_role: Optional[str] = None


class RoleUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    permissions: Optional[list[str]] = None


@router.get("/permissions")
async def list_permissions(user: dict = Depends(get_current_user)):
    """The catalog of available permission toggles (for the category editor)."""
    return {"permissions": [{"key": k, "label": l, "group": g} for k, l, g in PERMISSION_CATALOG]}


@router.get("/roles")
async def list_roles(user: dict = Depends(get_current_user)):
    """All non-deleted roles (built-in + custom). Powers role dropdowns + badges."""
    rows = await db.roles.find({"is_deleted": {"$ne": True}}, {"_id": 0}).to_list(1000)
    rows.sort(key=lambda r: (not r.get("is_system"), r.get("label", "")))
    return rows


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s or "role"


@router.post("/roles")
async def create_role(payload: RoleInput, user: dict = Depends(require_permission("roles.manage"))):
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Category name is required")
    perms = [p for p in (payload.permissions or []) if p in ALL_PERMISSIONS]
    key = _slug(label)
    base, i = key, 2
    while await db.roles.find_one({"key": key}):
        key = f"{base}_{i}"
        i += 1
    doc = {
        "key": key, "label": label, "color": payload.color or "#8A817C",
        "base_role": payload.base_role, "permissions": perms,
        "is_system": False, "is_deleted": False,
        "created_by": user["id"], "created_at": now_iso(),
    }
    await db.roles.insert_one(doc)
    await refresh_role_cache(db)
    await log_audit(db, user, "role.created", "role", key, label, {"permissions": perms})
    doc.pop("_id", None)
    return doc


@router.patch("/roles/{key}")
async def update_role(key: str, payload: RoleUpdate, user: dict = Depends(require_permission("roles.manage"))):
    role = await db.roles.find_one({"key": key})
    if not role:
        raise HTTPException(status_code=404, detail="Category not found")
    update: dict = {}
    if payload.label is not None:
        update["label"] = payload.label.strip()
    if payload.color is not None:
        update["color"] = payload.color
    if payload.permissions is not None:
        update["permissions"] = [p for p in payload.permissions if p in ALL_PERMISSIONS]
    if key == "ceo":
        update.pop("permissions", None)  # never strip the CEO super-set
    if update:
        await db.roles.update_one({"key": key}, {"$set": update})
        await refresh_role_cache(db)
        await log_audit(db, user, "role.updated", "role", key, update.get("label", role.get("label")), {"fields": list(update.keys())})
    return await db.roles.find_one({"key": key}, {"_id": 0})


@router.delete("/roles/{key}")
async def delete_role(key: str, user: dict = Depends(require_permission("roles.manage"))):
    role = await db.roles.find_one({"key": key})
    if not role:
        raise HTTPException(status_code=404, detail="Category not found")
    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="Built-in categories cannot be deleted")
    in_use = await db.users.count_documents({"role": key})
    if in_use:
        raise HTTPException(status_code=400, detail=f"{in_use} account(s) still use this category — reassign them first")
    # Soft delete: the record stays in the database for the record.
    await db.roles.update_one({"key": key}, {"$set": {"is_deleted": True}})
    await refresh_role_cache(db)
    await log_audit(db, user, "role.deleted", "role", key, role.get("label"), {})
    return {"ok": True}

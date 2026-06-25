"""
<module name="routers/users" layer="api">
  <purpose>User management. Listing is available to any authenticated user;
  creating/updating users is admin-only.</purpose>
  <endpoints>
    GET   /api/users            -> all users (passwords stripped).
    POST  /api/users            -> create user (admin). Default password from env.
    PATCH /api/users/{user_id}  -> update name/role/phone/is_active/password (admin).
  </endpoints>
</module>
"""
import os
import uuid
import secrets
from fastapi import APIRouter, HTTPException, Depends
from core import db, get_current_user, require_roles, UserCreate, ROLE_ADMIN, now_iso
from auth_utils import hash_password
from audit import log_audit

router = APIRouter()


def generate_password() -> str:
    """A readable, strong one-time password (e.g. 'k7Qm-3Tap-9Zx')."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)


@router.post("/users")
async def create_user(payload: UserCreate, admin: dict = Depends(require_roles(ROLE_ADMIN))):
    """Create an account (admin/CEO). If no password is supplied, a strong one is
    generated and returned ONCE so the admin can hand it to the new user."""
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    generated = None
    if payload.password:
        pwd = payload.password
    else:
        pwd = generate_password()
        generated = pwd
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(pwd),
        "full_name": payload.full_name,
        "role": payload.role,
        "phone": payload.phone,
        "is_active": True,
        "must_change_password": True,   # force a reset on first login
        "created_by": admin["id"],
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    await log_audit(db, admin, "user.created", "user", doc["id"], doc["full_name"], {"role": doc["role"], "email": doc["email"]})
    # generated_password is shown once in the UI; it is never stored in plaintext.
    return {**doc, "generated_password": generated}


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, admin: dict = Depends(require_roles(ROLE_ADMIN))):
    """Generate a fresh one-time password for an account; returned once to the admin."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    pwd = generate_password()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password_hash": hash_password(pwd), "must_change_password": True}},
    )
    await log_audit(db, admin, "user.password_reset", "user", user_id, target.get("full_name"), {})
    return {"id": user_id, "generated_password": pwd}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_roles(ROLE_ADMIN))):
    """Soft-delete: deactivate the account (preserves audit history). Cannot remove self."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"id": user_id}, {"$set": {"is_active": False}})
    await log_audit(db, admin, "user.deactivated", "user", user_id, target.get("full_name"), {})
    return {"ok": True}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: dict, admin: dict = Depends(require_roles(ROLE_ADMIN))):
    allowed = {"full_name", "role", "phone", "is_active"}
    update = {k: v for k, v in body.items() if k in allowed}
    if "password" in body and body["password"]:
        update["password_hash"] = hash_password(body["password"])
    if not update:
        return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await db.users.update_one({"id": user_id}, {"$set": update})
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await log_audit(db, admin, "user.updated", "user", user_id, target.get("full_name") if target else user_id, {"fields": list(update.keys())})
    return target

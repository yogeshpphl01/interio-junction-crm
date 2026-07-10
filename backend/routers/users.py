"""
<module name="routers/users" layer="api">
  <purpose>
    Account management. Listing is open to any signed-in user. Creating,
    deactivating and resetting passwords require ADMIN or CEO. Hard DELETE is
    CEO-only. The CEO super-account is protected: it can never be deactivated,
    deleted, demoted, or have its password reset by a non-CEO.
  </purpose>
  <endpoints>
    GET    /api/users                      -> all users (passwords stripped).
    POST   /api/users                      -> create (admin/ceo), returns one-time pwd.
    POST   /api/users/{id}/reset-password   -> new one-time password (admin/ceo).
    POST   /api/users/{id}/deactivate       -> disable login (admin/ceo).
    POST   /api/users/{id}/activate         -> re-enable login (admin/ceo).
    DELETE /api/users/{id}                  -> permanent delete (CEO only).
    PATCH  /api/users/{id}                  -> edit name/role/phone (admin/ceo).
  </endpoints>
</module>
"""
import uuid
import secrets
from fastapi import APIRouter, HTTPException, Depends
from core import (
    db, get_current_user, require_permission, UserCreate,
    ROLE_ADMIN, ROLE_CEO, BUILTIN_ROLES, now_iso,
)
from auth_utils import hash_password
from audit import log_audit

router = APIRouter()


def generate_password() -> str:
    """A readable, strong one-time password (e.g. 'k7Qm-3Tap-9Zx')."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


async def _valid_roles() -> set[str]:
    """Built-in roles plus any custom, not-deleted categories (Module 7)."""
    roles = set(BUILTIN_ROLES)
    async for r in db.roles.find({"is_deleted": {"$ne": True}}, {"key": 1, "_id": 0}):
        roles.add(r["key"])
    return roles


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)


@router.post("/users")
async def create_user(payload: UserCreate, admin: dict = Depends(require_permission("users.manage"))):
    """Create an account. If no password is supplied, a strong one is generated
    and returned ONCE so the admin can hand it over."""
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    if payload.role not in await _valid_roles():
        raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")
    if payload.role == ROLE_CEO and admin["role"] != ROLE_CEO:
        raise HTTPException(status_code=403, detail="Only a CEO can create another CEO account")
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
    return {**doc, "generated_password": generated}


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, admin: dict = Depends(require_permission("users.manage"))):
    """Generate a fresh one-time password; returned once. A CEO's password can
    only be reset by a CEO."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == ROLE_CEO and admin["role"] != ROLE_CEO:
        raise HTTPException(status_code=403, detail="Only a CEO can reset a CEO's password")
    pwd = generate_password()
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password_hash": hash_password(pwd), "must_change_password": True}},
    )
    await log_audit(db, admin, "user.password_reset", "user", user_id, target.get("full_name"), {})
    return {"id": user_id, "generated_password": pwd}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(user_id: str, admin: dict = Depends(require_permission("users.manage"))):
    """Disable login. The CEO account can never be deactivated; nor can you deactivate yourself."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == ROLE_CEO:
        raise HTTPException(status_code=403, detail="The CEO account cannot be deactivated")
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    await db.users.update_one({"id": user_id}, {"$set": {"is_active": False}})
    await log_audit(db, admin, "user.deactivated", "user", user_id, target.get("full_name"), {})
    return {"ok": True}


@router.post("/users/{user_id}/activate")
async def activate_user(user_id: str, admin: dict = Depends(require_permission("users.manage"))):
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"id": user_id}, {"$set": {"is_active": True}})
    await log_audit(db, admin, "user.reactivated", "user", user_id, target.get("full_name"), {})
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, ceo: dict = Depends(require_permission("users.delete"))):
    """Permanently delete an account (CEO only). The CEO account itself can never
    be deleted. The user's past actions remain in the immutable audit log."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("role") == ROLE_CEO:
        raise HTTPException(status_code=403, detail="The CEO account cannot be deleted")
    if user_id == ceo["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    await db.users.delete_one({"id": user_id})
    await log_audit(db, ceo, "user.deleted", "user", user_id, target.get("full_name"),
                    {"email": target.get("email"), "role": target.get("role")})
    return {"ok": True}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: dict, admin: dict = Depends(require_permission("users.manage"))):
    """Admin edit of another account's name / role / phone (and password)."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    allowed = {"full_name", "role", "phone", "reports_to"}
    update = {k: v for k, v in body.items() if k in allowed and v is not None}
    # Protect the CEO account from being demoted by anyone but a CEO.
    if target.get("role") == ROLE_CEO and "role" in update and update["role"] != ROLE_CEO and admin["role"] != ROLE_CEO:
        raise HTTPException(status_code=403, detail="Only a CEO can change a CEO's role")
    if "role" in update and update["role"] not in await _valid_roles():
        raise HTTPException(status_code=400, detail=f"Unknown role: {update['role']}")
    if "password" in body and body["password"]:
        update["password_hash"] = hash_password(body["password"])
    if not update:
        return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await db.users.update_one({"id": user_id}, {"$set": update})
    new = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await log_audit(db, admin, "user.updated", "user", user_id, new.get("full_name") if new else user_id, {"fields": list(update.keys())})
    return new

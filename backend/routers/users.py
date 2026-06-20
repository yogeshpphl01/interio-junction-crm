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
from fastapi import APIRouter, HTTPException, Depends
from core import db, get_current_user, require_roles, UserCreate, ROLE_ADMIN, now_iso
from auth_utils import hash_password
from audit import log_audit

router = APIRouter()


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)


@router.post("/users")
async def create_user(payload: UserCreate, admin: dict = Depends(require_roles(ROLE_ADMIN))):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    pwd = payload.password or os.environ.get("DEFAULT_USER_PASSWORD", "interio2026")
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(pwd),
        "full_name": payload.full_name,
        "role": payload.role,
        "phone": payload.phone,
        "is_active": True,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    await log_audit(db, admin, "user.created", "user", doc["id"], doc["full_name"], {"role": doc["role"], "email": doc["email"]})
    return doc


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

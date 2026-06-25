"""
<module name="routers/auth" layer="api">
  <purpose>Authentication endpoints.</purpose>
  <endpoints>
    POST /api/auth/login   -> verify credentials, set cookies, return user+tokens.
    POST /api/auth/logout  -> clear auth cookies.
    GET  /api/auth/me      -> current user (from token).
    POST /api/auth/refresh -> rotate access+refresh from a valid refresh cookie.
  </endpoints>
  <auditing>Both successful and failed logins are written to the audit log.</auditing>
</module>
"""
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from core import db, LoginInput, ChangePasswordInput, get_current_user
from auth_utils import (
    verify_password, hash_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, decode_token,
)
from audit import log_audit

router = APIRouter()


@router.post("/auth/login")
async def login(input: LoginInput, response: Response, request: Request):
    email = input.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("is_active", True):
        await log_audit(db, None, "auth.login_failed", "user", None, email, {"reason": "not_found_or_inactive"}, request)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(input.password, user["password_hash"]):
        await log_audit(db, None, "auth.login_failed", "user", user["id"], email, {"reason": "bad_password"}, request)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    user.pop("_id", None)
    user.pop("password_hash", None)
    await log_audit(db, user, "auth.login", "user", user["id"], user["full_name"], None, request)
    return {"user": user, "access_token": access, "refresh_token": refresh}


@router.post("/auth/logout")
async def logout(response: Response, request: Request, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    await log_audit(db, user, "auth.logout", "user", user["id"], user["full_name"], None, request)
    return {"ok": True}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/auth/change-password")
async def change_password(body: ChangePasswordInput, user: dict = Depends(get_current_user)):
    """Any logged-in user can change their own password (verifies the current one)."""
    if not body.new or len(body.new) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(body.current, full["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(body.new), "must_change_password": False}},
    )
    await log_audit(db, user, "user.password_changed", "user", user["id"], user.get("full_name"), {})
    return {"ok": True}


@router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access = create_access_token(user["id"], user["email"], user["role"])
    new_refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, new_refresh)
    return {"ok": True}

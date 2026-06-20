"""Auth: login, logout, me, refresh."""
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from core import db, LoginInput, get_current_user
from auth_utils import (
    verify_password, create_access_token, create_refresh_token,
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

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
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from core import (
    db, LoginInput, ChangePasswordInput, ProfileUpdate,
    ForgotPasswordInput, ResetPasswordInput, get_current_user,
)
from permissions import permissions_for, role_label, role_color
from auth_utils import (
    verify_password, hash_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, decode_token, create_mfa_pending_token,
)
from notifications import send_password_reset_otp
from audit import log_audit

router = APIRouter()

# <otp-policy> Self-service password reset tunables (email channel for now). </otp-policy>
OTP_TTL_MIN = 10            # a code is valid for 10 minutes
OTP_RESEND_COOLDOWN_SEC = 60  # ignore a resend within 60s of the last send
OTP_MAX_ATTEMPTS = 5         # lock the code after 5 wrong tries


def _generate_otp() -> str:
    """A 4-digit numeric one-time code (zero-padded)."""
    return f"{secrets.randbelow(10000):04d}"


# <lockout> Brute-force protection on password login (OWASP ASVS V2.2 / NIST
#   800-63B §5.2.2 / CWE-307). After LOGIN_MAX_FAILED wrong tries the account is
#   locked for a progressively longer window (doubling, capped). </lockout>
LOGIN_MAX_FAILED = 5
LOGIN_LOCK_BASE_MIN = 1
LOGIN_LOCK_CAP_MIN = 60


async def _register_login_failure(user: dict) -> None:
    cnt = (user.get("failed_login_count") or 0) + 1
    patch: dict = {"failed_login_count": cnt}
    if cnt >= LOGIN_MAX_FAILED:
        over = cnt - LOGIN_MAX_FAILED
        mins = min(LOGIN_LOCK_BASE_MIN * (2 ** over), LOGIN_LOCK_CAP_MIN)
        patch["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()
    await db.users.update_one({"id": user["id"]}, {"$set": patch})


@router.post("/auth/login")
async def login(input: LoginInput, response: Response, request: Request):
    email = input.email.lower().strip()
    user = await db.users.find_one({"email": email})
    now = datetime.now(timezone.utc)
    # Lockout is checked before the password so locked accounts can't be probed.
    if user and user.get("locked_until"):
        try:
            locked = datetime.fromisoformat(user["locked_until"])
        except (TypeError, ValueError):
            locked = None
        if locked and locked > now:
            await log_audit(db, None, "auth.login_failed", "user", user["id"], email, {"reason": "locked"}, request)
            raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")
    if not user or not user.get("is_active", True):
        await log_audit(db, None, "auth.login_failed", "user", None, email, {"reason": "not_found_or_inactive"}, request)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(input.password, user["password_hash"]):
        await _register_login_failure(user)
        await log_audit(db, None, "auth.login_failed", "user", user["id"], email, {"reason": "bad_password"}, request)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Success — clear any accumulated failure/lock state.
    if user.get("failed_login_count") or user.get("locked_until"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"failed_login_count": 0, "locked_until": None}})
    # If MFA is enrolled, the password is only the FIRST factor — issue a
    # short-lived pre-auth token and require /auth/mfa/verify before any access.
    if user.get("mfa_enrolled"):
        pending = create_mfa_pending_token(user["id"])
        await log_audit(db, None, "auth.login", "user", user["id"], user["full_name"], {"mfa_required": True}, request)
        return {"mfa_required": True, "mfa_token": pending}
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    user.pop("_id", None)
    user.pop("password_hash", None)
    user["permissions"] = permissions_for(user["role"])
    user["role_label"] = role_label(user["role"])
    user["role_color"] = role_color(user["role"])
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


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordInput, request: Request):
    """Step 1 — issue a one-time reset code to the account's recovery email.

    Always returns the same generic response so the endpoint never reveals whether
    an email exists or has a recovery address on file. A code is only generated +
    sent when the account is active and has a recovery_email, and not more often
    than the resend cooldown."""
    email = body.email.lower().strip()
    generic = {"ok": True, "message": "If an account with a recovery email exists, a reset code has been sent."}
    user = await db.users.find_one({"email": email})
    if not user or not user.get("is_active", True) or not user.get("recovery_email"):
        return generic

    now = datetime.now(timezone.utc)
    # Anti-spam: don't mint/send another code if ANY code was sent within the
    # cooldown window (regardless of whether it was used or locked out).
    rows = await db.password_resets.find({"user_id": user["id"]}).sort("created_at", -1).to_list(1)
    latest = rows[0] if rows else None
    if latest and latest.get("sent_at"):
        try:
            if (now - datetime.fromisoformat(latest["sent_at"])).total_seconds() < OTP_RESEND_COOLDOWN_SEC:
                return generic  # silently respect the cooldown
        except Exception:
            pass

    code = _generate_otp()
    await db.password_resets.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "otp_hash": hash_password(code),
        "expires_at": (now + timedelta(minutes=OTP_TTL_MIN)).isoformat(),
        "attempts": 0,
        "sent_at": now.isoformat(),
        "consumed": False,
        "created_at": now.isoformat(),
    })
    ok, info = await send_password_reset_otp(user["recovery_email"], code, user.get("full_name"))
    await log_audit(db, None, "auth.password_reset_requested", "user", user["id"], user.get("full_name"),
                    {"channel": "email", "delivered": ok, "info": info}, request)
    return generic


@router.post("/auth/reset-password")
async def reset_password_with_otp(body: ResetPasswordInput, request: Request):
    """Step 2 — verify the OTP and set a new password.

    A single generic error is returned for every failure (wrong/expired/locked
    code, unknown email) so nothing about the account is leaked."""
    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    invalid = HTTPException(status_code=400, detail="Invalid or expired code")
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user:
        raise invalid

    rows = await db.password_resets.find({"user_id": user["id"]}).sort("created_at", -1).to_list(1)
    rec = rows[0] if rows else None
    if not rec or rec.get("consumed"):
        raise invalid
    now = datetime.now(timezone.utc)
    try:
        expired = datetime.fromisoformat(rec["expires_at"]) < now
    except Exception:
        expired = True
    if expired:
        await db.password_resets.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
        raise invalid
    if (rec.get("attempts") or 0) >= OTP_MAX_ATTEMPTS:
        await db.password_resets.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
        raise invalid

    if not verify_password(body.otp.strip(), rec["otp_hash"]):
        attempts = (rec.get("attempts") or 0) + 1
        patch = {"attempts": attempts}
        if attempts >= OTP_MAX_ATTEMPTS:
            patch["consumed"] = True  # lock the code after too many tries
        await db.password_resets.update_one({"id": rec["id"]}, {"$set": patch})
        await log_audit(db, None, "auth.password_reset_failed", "user", user["id"], user.get("full_name"),
                        {"attempts": attempts, "locked": attempts >= OTP_MAX_ATTEMPTS}, request)
        raise invalid

    # Success — set the new password and burn the code.
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(body.new_password), "must_change_password": False}},
    )
    await db.password_resets.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
    await log_audit(db, user, "auth.password_reset_completed", "user", user["id"], user.get("full_name"), {}, request)
    return {"ok": True, "message": "Password updated. You can now sign in with your new password."}


@router.patch("/auth/profile")
async def update_own_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    """Module 1.4 — any user edits their OWN personal details (name/phone/recovery
    email). Every change is written to the immutable audit log (before -> after)."""
    full = await db.users.find_one({"id": user["id"]})
    update, changes = {}, {}
    for field in ("full_name", "phone", "recovery_email"):
        val = getattr(body, field)
        if val is not None and val != full.get(field):
            update[field] = val
            changes[field] = {"from": full.get(field), "to": val}
    if not update:
        return await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    await db.users.update_one({"id": user["id"]}, {"$set": update})
    await log_audit(db, user, "user.profile_updated", "user", user["id"], update.get("full_name", user.get("full_name")), {"changes": changes})
    return await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})


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

"""
<module name="routers/mfa" layer="api">
  <purpose>
    Staff MFA (TOTP) — enroll, activate, complete login, step-up, disable
    (NIST 800-63B AAL2 / OWASP MASVS-AUTH / ASVS V2.8). Second factor is a
    RFC-6238 authenticator code (replay-protected) or a one-time backup code.
    Passwordless customers are unaffected (they use phone OTP + biometric step-up
    in the Client App).
  </purpose>
</module>
"""
import secrets as _secrets
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel

from core import db, get_current_user
from auth_utils import (
    hash_password, verify_password, decode_token,
    create_access_token, create_refresh_token, set_auth_cookies, create_step_up_token,
    STEP_UP_TTL_MIN,
)
from permissions import permissions_for, role_label, role_color
import totp
from audit import log_audit

router = APIRouter()

BACKUP_CODE_COUNT = 10


def _gen_backup_code() -> str:
    return _secrets.token_hex(5)  # 10 hex chars, single-use


class CodeIn(BaseModel):
    code: str


class MfaVerifyIn(BaseModel):
    mfa_token: str
    code: str


async def _check_second_factor(user: dict, code: str) -> tuple[bool, str]:
    """Verify a TOTP code (replay-protected via mfa_last_step) or a one-time backup code."""
    code = (code or "").strip()
    secret = user.get("mfa_secret")
    if secret and len(code) == totp.DIGITS and code.isdigit():
        step = totp.verify(secret, code)
        if step is not None:
            if step <= (user.get("mfa_last_step") or 0):
                return False, "totp_replay"      # this step (or earlier) already used
            await db.users.update_one({"id": user["id"]}, {"$set": {"mfa_last_step": step}})
            return True, "totp"
    for entry in (user.get("mfa_backup_codes") or []):
        if not entry.get("used") and verify_password(code, entry["hash"]):
            entry["used"] = True
            await db.users.update_one({"id": user["id"]}, {"$set": {"mfa_backup_codes": user["mfa_backup_codes"]}})
            return True, "backup_code"
    return False, "none"


def _issue_full_session(user: dict):
    tv = int(user.get("token_version") or 0)
    access = create_access_token(user["id"], user["email"], user["role"], aal=2, amr=["pwd", "otp"], tv=tv)
    refresh = create_refresh_token(user["id"], tv=tv)
    u = {k: v for k, v in user.items()
         if k not in ("_id", "password_hash", "mfa_secret", "mfa_backup_codes")}
    u["permissions"] = permissions_for(user["role"])
    u["role_label"] = role_label(user["role"])
    u["role_color"] = role_color(user["role"])
    return access, refresh, u


@router.post("/auth/mfa/enroll")
async def mfa_enroll(user: dict = Depends(get_current_user)):
    """Begin enrollment: generate a secret (not yet active) and return the otpauth URI to QR."""
    if user.get("mfa_enrolled"):
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    secret = totp.generate_secret()
    await db.users.update_one({"id": user["id"]}, {"$set": {"mfa_secret": secret, "mfa_enrolled": False}})
    return {
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, user["email"]),
        "digits": totp.DIGITS, "period": totp.PERIOD,
    }


@router.post("/auth/mfa/activate")
async def mfa_activate(body: CodeIn, request: Request, user: dict = Depends(get_current_user)):
    """Confirm the first code to enable MFA; returns one-time backup codes (shown once)."""
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if full.get("mfa_enrolled"):
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    secret = full.get("mfa_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="Start enrollment first")
    step = totp.verify(secret, body.code)
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid code")
    codes = [_gen_backup_code() for _ in range(BACKUP_CODE_COUNT)]
    hashed = [{"hash": hash_password(c), "used": False} for c in codes]
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "mfa_enrolled": True, "mfa_last_step": step, "mfa_backup_codes": hashed,
    }})
    await log_audit(db, user, "auth.mfa_enrolled", "user", user["id"], user.get("full_name"), None, request)
    return {"enabled": True, "backup_codes": codes}


@router.post("/auth/mfa/verify")
async def mfa_verify(body: MfaVerifyIn, request: Request, response: Response):
    """Complete login: pre-auth token + TOTP/backup code -> full AAL2 session."""
    invalid = HTTPException(status_code=401, detail="Invalid or expired MFA token")
    try:
        payload = decode_token(body.mfa_token)
    except HTTPException:
        raise invalid
    if payload.get("type") != "mfa_pending":
        raise invalid
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or not user.get("is_active", True) or not user.get("mfa_enrolled"):
        raise invalid
    ok, method = await _check_second_factor(user, body.code)
    if not ok:
        await log_audit(db, None, "auth.mfa_failed", "user", user["id"], user.get("full_name"), {"method": method}, request)
        raise HTTPException(status_code=400, detail="Invalid code")
    access, refresh, u = _issue_full_session(user)
    set_auth_cookies(response, access, refresh)
    await log_audit(db, u, "auth.mfa_verified", "user", user["id"], user.get("full_name"), {"method": method}, request)
    return {"user": u, "access_token": access, "refresh_token": refresh}


@router.post("/auth/mfa/step-up")
async def mfa_step_up(body: CodeIn, request: Request, user: dict = Depends(get_current_user)):
    """Re-verify the second factor for a sensitive action; returns a short elevation token
    (send it as X-Step-Up-Token on the protected request)."""
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not full.get("mfa_enrolled"):
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    ok, method = await _check_second_factor(full, body.code)
    if not ok:
        await log_audit(db, None, "auth.mfa_failed", "user", user["id"], user.get("full_name"), {"context": "step_up"}, request)
        raise HTTPException(status_code=400, detail="Invalid code")
    await log_audit(db, user, "auth.mfa_step_up", "user", user["id"], user.get("full_name"), {"method": method}, request)
    return {"elevation_token": create_step_up_token(user["id"]), "expires_in": STEP_UP_TTL_MIN * 60}


@router.post("/auth/mfa/disable")
async def mfa_disable(body: CodeIn, request: Request, user: dict = Depends(get_current_user)):
    """Turn MFA off — requires a current second factor (never silent)."""
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not full.get("mfa_enrolled"):
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    ok, _ = await _check_second_factor(full, body.code)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid code")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "mfa_enrolled": False, "mfa_secret": None, "mfa_backup_codes": None, "mfa_last_step": None,
    }})
    await log_audit(db, user, "auth.mfa_disabled", "user", user["id"], user.get("full_name"), None, request)
    return {"enabled": False}


@router.get("/auth/mfa/status")
async def mfa_status(user: dict = Depends(get_current_user)):
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    remaining = sum(1 for c in (full.get("mfa_backup_codes") or []) if not c.get("used"))
    return {"enrolled": bool(full.get("mfa_enrolled")), "aal": user.get("aal", 1), "backup_codes_remaining": remaining}

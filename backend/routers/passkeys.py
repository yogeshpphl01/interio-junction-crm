"""
<module name="routers/passkeys" layer="api">
  <purpose>
    Phishing-resistant login for staff (esp. admin/CEO) via WebAuthn / FIDO2
    passkeys — NIST 800-63B AAL2/AAL3, OWASP MASVS-AUTH. Registration and
    authentication ceremonies are verified by py_webauthn. A passkey login mints
    a full session with amr=["webauthn"], aal=2.
  </purpose>
  <config>
    WEBAUTHN_RP_ID (e.g. "app.interiojunction.com"), WEBAUTHN_ORIGIN
    (e.g. "https://app.interiojunction.com"), WEBAUTHN_RP_NAME. Defaults suit
    local dev (localhost). Passkeys require HTTPS + a matching RP ID/origin.
  </config>
</module>
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel

import webauthn
from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json, base64url_to_bytes,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, ResidentKeyRequirement, UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)

from core import db, get_current_user, now_iso
from auth_utils import create_access_token, create_refresh_token, set_auth_cookies
from permissions import permissions_for, role_label, role_color
from audit import log_audit
import json as _json

router = APIRouter()

RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Interio Junction CRM")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "http://localhost")
CHALLENGE_TTL_MIN = 5


class EmailIn(BaseModel):
    email: str


class CredentialIn(BaseModel):
    credential: dict
    label: str | None = None


async def _store_challenge(user_id: str, kind: str, challenge: bytes) -> None:
    await db.webauthn_challenges.delete_one({"user_id": user_id, "kind": kind})
    await db.webauthn_challenges.insert_one({
        "id": str(uuid.uuid4()), "user_id": user_id, "kind": kind,
        "challenge": bytes_to_base64url(challenge),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_TTL_MIN)).isoformat(),
        "created_at": now_iso(),
    })


async def _consume_challenge(user_id: str, kind: str) -> bytes | None:
    row = await db.webauthn_challenges.find_one({"user_id": user_id, "kind": kind}, {"_id": 0})
    if not row:
        return None
    await db.webauthn_challenges.delete_one({"user_id": user_id, "kind": kind})
    try:
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
    except Exception:
        return None
    return base64url_to_bytes(row["challenge"])


@router.post("/auth/passkey/register/options")
async def register_options(user: dict = Depends(get_current_user)):
    """Begin passkey enrollment for the signed-in staff member."""
    opts = generate_registration_options(
        rp_id=RP_ID, rp_name=RP_NAME,
        user_id=user["id"].encode(), user_name=user["email"],
        user_display_name=user.get("full_name") or user["email"],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    await _store_challenge(user["id"], "register", opts.challenge)
    return _json.loads(options_to_json(opts))


@router.post("/auth/passkey/register/verify")
async def register_verify(body: CredentialIn, request: Request, user: dict = Depends(get_current_user)):
    challenge = await _consume_challenge(user["id"], "register")
    if not challenge:
        raise HTTPException(status_code=400, detail="No pending registration — start again")
    try:
        v = verify_registration_response(
            credential=body.credential, expected_challenge=challenge,
            expected_rp_id=RP_ID, expected_origin=ORIGIN,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Passkey registration failed")
    await db.webauthn_credentials.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"],
        "credential_id": bytes_to_base64url(v.credential_id),
        "public_key": bytes_to_base64url(v.credential_public_key),
        "sign_count": int(v.sign_count or 0),
        "transports": ",".join(body.credential.get("response", {}).get("transports", []) or []),
        "label": body.label or "Passkey", "created_at": now_iso(), "last_used_at": None,
    })
    await log_audit(db, user, "auth.passkey_registered", "user", user["id"], user.get("full_name"), None, request)
    return {"registered": True}


@router.get("/auth/passkey/list")
async def list_passkeys(user: dict = Depends(get_current_user)):
    rows = await db.webauthn_credentials.find({"user_id": user["id"]},
                                              {"_id": 0, "public_key": 0}).to_list(50)
    return {"passkeys": rows}


@router.delete("/auth/passkey/{cred_id}")
async def delete_passkey(cred_id: str, user: dict = Depends(get_current_user)):
    rec = await db.webauthn_credentials.find_one({"id": cred_id}, {"_id": 0, "user_id": 1})
    if not rec or rec.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Passkey not found")
    await db.webauthn_credentials.delete_one({"id": cred_id})
    return {"ok": True}


@router.post("/auth/passkey/login/options")
async def login_options(body: EmailIn):
    """Begin passkey login. The response is the same shape whether or not the
    email exists / has passkeys (no account enumeration)."""
    email = (body.email or "").lower().strip()
    user = await db.users.find_one({"email": email})
    allow = None
    if user and user.get("is_active", True):
        rows = await db.webauthn_credentials.find({"user_id": user["id"]}, {"_id": 0, "credential_id": 1}).to_list(20)
        if rows:
            allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(r["credential_id"])) for r in rows]
    opts = generate_authentication_options(rp_id=RP_ID, allow_credentials=allow)
    if user:
        await _store_challenge(user["id"], "auth", opts.challenge)
    return _json.loads(options_to_json(opts))


@router.post("/auth/passkey/login/verify")
async def login_verify(body: CredentialIn, request: Request, response: Response):
    invalid = HTTPException(status_code=400, detail="Passkey authentication failed")
    cred = body.credential or {}
    raw_id = cred.get("rawId") or cred.get("id")
    if not raw_id:
        raise invalid
    rec = await db.webauthn_credentials.find_one({"credential_id": raw_id}, {"_id": 0})
    if not rec:
        raise invalid
    user = await db.users.find_one({"id": rec["user_id"]})
    if not user or not user.get("is_active", True):
        raise invalid
    challenge = await _consume_challenge(user["id"], "auth")
    if not challenge:
        raise invalid
    try:
        v = verify_authentication_response(
            credential=cred, expected_challenge=challenge,
            expected_rp_id=RP_ID, expected_origin=ORIGIN,
            credential_public_key=base64url_to_bytes(rec["public_key"]),
            credential_current_sign_count=int(rec.get("sign_count") or 0),
        )
    except Exception:
        raise invalid
    await db.webauthn_credentials.update_one({"id": rec["id"]}, {"$set": {
        "sign_count": int(v.new_sign_count), "last_used_at": now_iso(),
    }})
    tv = int(user.get("token_version") or 0)
    access = create_access_token(user["id"], user["email"], user["role"], aal=2, amr=["webauthn"], tv=tv)
    refresh = create_refresh_token(user["id"], tv=tv)
    set_auth_cookies(response, access, refresh)
    u = {k: v2 for k, v2 in user.items() if k not in ("_id", "password_hash", "mfa_secret", "mfa_backup_codes")}
    u["permissions"] = permissions_for(user["role"])
    u["role_label"] = role_label(user["role"])
    u["role_color"] = role_color(user["role"])
    await log_audit(db, u, "auth.passkey_login", "user", user["id"], user.get("full_name"), None, request)
    return {"user": u, "access_token": access, "refresh_token": refresh}

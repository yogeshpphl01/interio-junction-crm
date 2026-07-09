"""
<module name="routers/client" layer="api-bff">
  <purpose>
    The Client App BFF (mobile ecosystem, P0). This is the customer-facing half
    of the dual-BFF boundary: every route here authenticates a CUSTOMER (not an
    employee) via get_current_customer, so company/RBAC endpoints and these
    customer endpoints can never be reached with the wrong identity's token.

    Auth is phone + one-time code (OTP), which mirrors the eventual Firebase
    phone-auth migration: only the OTP-verify step changes then (swap the local
    code check for a Firebase ID-token verification) — the customer record, the
    customer JWT, and every route below stay identical.

    A customer is always anchored to real CRM data: a login code is only issued
    for a phone that already exists as a lead, so there is no open self-signup
    and every customer maps to a known prospect/client. On first verify we create
    the customer record and stamp customer_id onto all of that phone's leads, so
    the scoped reads below are simple indexed lookups.
  </purpose>
  <endpoints>
    POST /client/auth/request-otp   issue a login code (generic response; no enumeration)
    POST /client/auth/verify-otp    verify code -> customer JWT (access + refresh)
    POST /client/auth/refresh       new access token from a customer refresh token
    POST /client/auth/logout        audit-only (mobile just drops the bearer token)
    GET  /client/me                 the authenticated customer's profile
    GET  /client/projects           the customer's lead(s) + project status
    GET  /client/estimates          the customer's SHARED/ACCEPTED estimates (never drafts)
    POST /client/estimates/{id}/accept  customer accepts their own shared estimate
  </endpoints>
</module>
"""
import uuid
import logging
import secrets
from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import db, get_current_customer, now_iso, STAGES
from auth_utils import (
    hash_password, verify_password, decode_token,
    create_customer_access_token, create_customer_refresh_token,
)
from audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter()

# <otp-policy> Client App login-code tunables. Mirrors the CRM reset policy. </otp-policy>
OTP_TTL_MIN = 10               # a code is valid for 10 minutes
OTP_RESEND_COOLDOWN_SEC = 60   # ignore a resend within 60s of the last send
OTP_MAX_ATTEMPTS = 5           # lock the code after 5 wrong tries

# Estimate states a customer is allowed to see (internal drafts stay hidden).
CLIENT_VISIBLE_ESTIMATE_STATES = ["shared", "accepted"]

_STAGE_BY_ID = {s["id"]: s for s in STAGES}


def _generate_otp() -> str:
    """A 4-digit numeric one-time code (zero-padded)."""
    return f"{secrets.randbelow(10000):04d}"


def normalize_phone(raw) -> str:
    """
    Canonical phone for matching + uniqueness: the last 10 digits (Indian mobile).
    '+91 98765 11111' and '98765 11111' both collapse to '9876511111'. Returns ''
    for anything shorter than 10 digits. (A phone_normalized column on leads is the
    scale-up path; at ~20 customers/month a login-time scan is negligible.)
    """
    if not raw:
        return ""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


async def _deliver_customer_otp(phone: str, code: str, name: Optional[str]) -> None:
    """
    Delivery seam. No SMS/WhatsApp gateway is wired yet, so the code is logged
    (dev) exactly like the CRM's email-reset stub. Swapping in an SMS/WhatsApp
    provider — or Firebase phone auth — is a one-function change here.
    """
    logger.info(f"[Client OTP] {phone} -> {code} (valid {OTP_TTL_MIN}m){' for ' + name if name else ''}")


async def _leads_for_phone(norm: str) -> list[dict]:
    """Every lead whose phone matches this normalized number."""
    if not norm:
        return []
    rows = await db.leads.find({}, {"_id": 0, "id": 1, "phone": 1, "full_name": 1, "email": 1}).to_list(20000)
    return [r for r in rows if normalize_phone(r.get("phone")) == norm]


async def _get_or_create_customer(norm_phone: str, leads: list[dict]) -> dict:
    """Fetch the customer for this phone, or create one anchored to their first lead."""
    existing = await db.customers.find_one({"phone": norm_phone}, {"_id": 0})
    if existing:
        return existing
    primary = leads[0]
    email = (primary.get("email") or "").strip() or None
    # Respect the unique-email index: drop the email if another customer already has it.
    if email and await db.customers.find_one({"email": email}):
        email = None
    doc = {
        "id": str(uuid.uuid4()),
        "lead_id": primary["id"],
        "full_name": (primary.get("full_name") or "Customer"),
        "phone": norm_phone,
        "email": email,
        "auth_uid": None,          # reserved for the Firebase UID after migration
        "is_active": True,
        "last_login_at": None,
        "created_at": now_iso(),
    }
    await db.customers.insert_one(doc)
    return doc


async def _my_lead_ids(customer: dict) -> list[str]:
    rows = await db.leads.find({"customer_id": customer["id"]}, {"_id": 0, "id": 1}).to_list(1000)
    return [r["id"] for r in rows]


def _stage_view(stage) -> dict:
    s = _STAGE_BY_ID.get(int(stage or 1), _STAGE_BY_ID[1])
    return {"stage": s["id"], "stage_name": s["name"], "stage_color": s["color"]}


# ============================ AUTH ============================

class RequestOtpIn(BaseModel):
    phone: str


class VerifyOtpIn(BaseModel):
    phone: str
    code: str


class RefreshIn(BaseModel):
    refresh_token: Optional[str] = None


@router.post("/client/auth/request-otp")
async def request_otp(body: RequestOtpIn, request: Request):
    """
    Step 1 — issue a login code to a registered phone. The response is always the
    same generic message so an attacker cannot use it to discover which numbers
    are customers; a code is only actually generated when the phone matches a lead.
    """
    generic = {"ok": True, "message": "If your number is registered with us, a login code has been sent."}
    norm = normalize_phone(body.phone)
    if not norm:
        return generic
    leads = await _leads_for_phone(norm)
    if not leads:
        return generic  # unknown number: reveal nothing, send nothing

    now = datetime.now(timezone.utc)
    # Resend cooldown: honour only the most recent code row for this phone.
    rows = await db.customer_otps.find({"phone": norm}).sort("created_at", -1).to_list(1)
    if rows and rows[0].get("sent_at"):
        if (now - datetime.fromisoformat(rows[0]["sent_at"])).total_seconds() < OTP_RESEND_COOLDOWN_SEC:
            return generic  # silently respect the cooldown

    code = _generate_otp()
    await db.customer_otps.insert_one({
        "id": str(uuid.uuid4()),
        "phone": norm,
        "otp_hash": hash_password(code),
        "expires_at": (now + timedelta(minutes=OTP_TTL_MIN)).isoformat(),
        "attempts": 0,
        "sent_at": now.isoformat(),
        "consumed": False,
        "created_at": now.isoformat(),
    })
    await _deliver_customer_otp(norm, code, leads[0].get("full_name"))
    await log_audit(db, None, "client.otp_requested", "customer", None, norm, {"leads": len(leads)}, request)
    return generic


@router.post("/client/auth/verify-otp")
async def verify_otp(body: VerifyOtpIn, request: Request):
    """Step 2 — verify the code and mint a customer session (access + refresh)."""
    invalid = HTTPException(status_code=400, detail="Invalid or expired code")
    norm = normalize_phone(body.phone)
    if not norm:
        raise invalid
    leads = await _leads_for_phone(norm)
    if not leads:
        raise invalid

    now = datetime.now(timezone.utc)
    rows = await db.customer_otps.find({"phone": norm}).sort("created_at", -1).to_list(1)
    if not rows:
        raise invalid
    rec = rows[0]
    if rec.get("consumed"):
        raise invalid
    if datetime.fromisoformat(rec["expires_at"]) < now:
        await db.customer_otps.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
        raise invalid
    if (rec.get("attempts") or 0) >= OTP_MAX_ATTEMPTS:
        await db.customer_otps.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
        raise invalid
    if not verify_password(body.code.strip(), rec["otp_hash"]):
        attempts = (rec.get("attempts") or 0) + 1
        patch = {"attempts": attempts}
        if attempts >= OTP_MAX_ATTEMPTS:
            patch["consumed"] = True
        await db.customer_otps.update_one({"id": rec["id"]}, {"$set": patch})
        await log_audit(db, None, "client.otp_failed", "customer", None, norm,
                        {"attempts": attempts, "locked": attempts >= OTP_MAX_ATTEMPTS}, request)
        raise invalid

    # Success: consume the code, resolve the customer, and link their leads.
    await db.customer_otps.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
    customer = await _get_or_create_customer(norm, leads)
    for lid in [l["id"] for l in leads]:
        await db.leads.update_one({"id": lid}, {"$set": {"customer_id": customer["id"]}})
    await db.customers.update_one({"id": customer["id"]}, {"$set": {"last_login_at": now_iso()}})

    access = create_customer_access_token(customer["id"], customer["phone"])
    refresh = create_customer_refresh_token(customer["id"])
    await log_audit(db, None, "client.login", "customer", customer["id"], customer.get("full_name"),
                    {"phone": norm}, request)
    customer.pop("_id", None)
    return {"customer": customer, "access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/client/auth/refresh")
async def refresh_client_token(body: RefreshIn, request: Request):
    """Exchange a customer refresh token for a fresh access token."""
    token = body.refresh_token or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    payload = decode_token(token)
    if payload.get("type") != "customer_refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    customer = await db.customers.find_one({"id": payload["sub"]}, {"_id": 0})
    if not customer or not customer.get("is_active", True):
        raise HTTPException(status_code=401, detail="Customer not found or inactive")
    access = create_customer_access_token(customer["id"], customer["phone"])
    return {"access_token": access, "token_type": "bearer"}


@router.post("/client/auth/logout")
async def client_logout(request: Request, customer: dict = Depends(get_current_customer)):
    """Bearer tokens are stateless; this just records the event for the audit trail."""
    await log_audit(db, None, "client.logout", "customer", customer["id"], customer.get("full_name"), None, request)
    return {"ok": True}


@router.get("/client/me")
async def client_me(customer: dict = Depends(get_current_customer)):
    return {"customer": customer}


# ============================ SCOPED READS + ACTIONS ============================

@router.get("/client/projects")
async def client_projects(customer: dict = Depends(get_current_customer)):
    """The customer's own lead(s) with pipeline stage and (once activated) project status."""
    leads = await db.leads.find({"customer_id": customer["id"]}, {"_id": 0}).to_list(1000)
    out = []
    for l in leads:
        proj = None
        if l.get("project_id"):
            pr = await db.projects.find_one({"id": l["project_id"]}, {"_id": 0})
            if pr:
                proj = {
                    "project_code": pr.get("project_code"),
                    "contract_value": pr.get("contract_value"),
                    "booking_paid": bool(pr.get("booking_paid")),
                    "activated_at": pr.get("activated_at"),
                    "in_production": bool(pr.get("sent_to_factory")),
                }
        out.append({
            "lead_id": l["id"],
            "full_name": l.get("full_name"),
            "requirements": l.get("requirements"),
            "bhk_type": l.get("bhk_type"),
            "status": l.get("status"),
            "lifecycle_phase": l.get("lifecycle_phase"),
            **_stage_view(l.get("stage")),
            "project": proj,
        })
    return {"projects": out}


@router.get("/client/estimates")
async def client_estimates(customer: dict = Depends(get_current_customer)):
    """The customer's shared/accepted estimates with line items. Drafts stay internal."""
    lead_ids = await _my_lead_ids(customer)
    if not lead_ids:
        return {"estimates": []}
    rows = await db.estimates.find(
        {"lead_id": {"$in": lead_ids}, "status": {"$in": CLIENT_VISIBLE_ESTIMATE_STATES}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    out = []
    for e in rows:
        items = await db.estimate_items.find({"estimate_id": e["id"]}, {"_id": 0}).to_list(500)
        out.append({**e, "items": items})
    return {"estimates": out}


@router.post("/client/estimates/{estimate_id}/accept")
async def client_accept_estimate(estimate_id: str, request: Request,
                                 customer: dict = Depends(get_current_customer)):
    """
    The customer accepts their own SHARED estimate — the same transition the SE
    could record on their behalf, now driven by the customer directly (§16). This
    is what unlocks the 10% booking payment. Strictly scoped: the estimate's lead
    must belong to this customer, and a 404 (not 403) hides anything that doesn't.
    """
    est = await db.estimates.find_one({"id": estimate_id}, {"_id": 0})
    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")
    lead = await db.leads.find_one({"id": est["lead_id"]}, {"_id": 0})
    if not lead or lead.get("customer_id") != customer["id"]:
        raise HTTPException(status_code=404, detail="Estimate not found")

    if est["status"] == "accepted":
        return {"ok": True, "estimate_id": estimate_id, "status": "accepted"}  # idempotent
    if est["status"] != "shared":
        raise HTTPException(status_code=409, detail="This estimate is not available to accept")

    ts = now_iso()
    await db.estimates.update_one({"id": estimate_id}, {"$set": {"status": "accepted", "updated_at": ts}})
    await db.activities.insert_one({
        "id": str(uuid.uuid4()), "lead_id": est["lead_id"], "type": "Note",
        "summary": f"Customer accepted estimate v{est.get('version')} via the Client App.",
        "actor_id": None, "created_at": ts,
    })
    await log_audit(db, None, "estimate.accepted", "estimate", estimate_id, f"v{est.get('version')}",
                    {"lead_id": est["lead_id"], "channel": "client_app", "customer_id": customer["id"]}, request)
    return {"ok": True, "estimate_id": estimate_id, "status": "accepted"}

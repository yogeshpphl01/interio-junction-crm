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
import os
import uuid
import logging
import secrets
from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import (
    db, get_current_customer, now_iso, STAGES, run_workflow_notify_designer,
    revoke_tokens, assert_client_step_up,
)
from app_check import require_app_check
from auth_utils import (
    hash_password, verify_password, decode_token, otp_debug_logging,
    create_customer_access_token, create_customer_refresh_token,
    create_doc_download_token, DOC_URL_TTL_MIN,
    create_customer_step_up_token, STEP_UP_TTL_MIN,
)
from file_validation import safe_filename
from audit import log_audit
from push import register_device, unregister_device

logger = logging.getLogger(__name__)
router = APIRouter()

# <otp-policy> Client App login-code tunables. Mirrors the CRM reset policy. </otp-policy>
OTP_TTL_MIN = 10               # a code is valid for 10 minutes
OTP_RESEND_COOLDOWN_SEC = 60   # ignore a resend within 60s of the last send
OTP_MAX_ATTEMPTS = 5           # lock the code after 5 wrong tries
OTP_MAX_PER_DAY = 10           # cap requests per phone / 24h (anti SMS-bombing)

# Estimate states a customer is allowed to see (internal drafts stay hidden).
CLIENT_VISIBLE_ESTIMATE_STATES = ["shared", "accepted"]
# Design revisions the customer may see (Draft / internal Pending stay hidden).
CLIENT_VISIBLE_REVISION_STATES = ["Shared", "Approved", "Revision Requested"]
# Document types appropriate for the customer (manufacturing docs stay internal:
# Cutlist / BOM / BOQ / Site Measurement Sheet are never exposed).
CLIENT_VISIBLE_DOC_TYPES = ["2D CAD", "3D Render", "Design File", "Quotation PDF", "Site Photo"]
# Payment statuses that count as money actually received.
PAID_PAYMENT_STATES = ["verified", "paid", "Paid"]

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
    if otp_debug_logging():
        logger.info(f"[Client OTP] {phone} -> {code} (valid {OTP_TTL_MIN}m){' for ' + name if name else ''}")
    else:
        # Production: never log the code (or the full number). Real delivery goes
        # through the SMS/WhatsApp/Firebase seam once configured.
        logger.info(f"[Client OTP] code issued for ***{phone[-4:] if phone else ''} (delivery pending; set OTP_DEBUG_LOG in dev)")


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


async def _my_project_ids(customer: dict) -> list[str]:
    rows = await db.leads.find({"customer_id": customer["id"]}, {"_id": 0, "project_id": 1}).to_list(1000)
    return [r["project_id"] for r in rows if r.get("project_id")]


def _doc_view(d: dict) -> dict:
    """Customer-safe document metadata. The internal storage_path is NOT exposed;
    the app fetches bytes via GET /client/documents/{id}/signed-url, which mints a
    short-lived signed download URL (P1-10)."""
    return {
        "id": d["id"], "type": d.get("type"), "filename": d.get("original_filename"),
        "content_type": d.get("content_type"), "size": d.get("size"),
        "created_at": d.get("created_at"),
    }


def _payment_view(p: dict) -> dict:
    return {
        "id": p["id"], "type": p.get("type") or "milestone", "milestone": p.get("milestone"),
        "amount": p.get("amount"), "currency": p.get("currency") or "INR",
        "status": p.get("status"), "method": p.get("method"),
        "due_date": p.get("due_date"), "paid_date": p.get("paid_date"),
    }


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
async def request_otp(body: RequestOtpIn, request: Request, _ac: None = Depends(require_app_check)):
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
    rows = await db.customer_otps.find({"phone": norm}).sort("created_at", -1).to_list(50)
    # Resend cooldown: honour only the most recent code row for this phone.
    if rows and rows[0].get("sent_at"):
        if (now - datetime.fromisoformat(rows[0]["sent_at"])).total_seconds() < OTP_RESEND_COOLDOWN_SEC:
            return generic  # silently respect the cooldown
    # Daily cap per phone (anti SMS-bombing / abuse). Per-IP + global caps belong
    # at the gateway (Cloud Armor) — see MOBILE_SECURITY_STANDARDS I1/I2.
    day_ago = (now - timedelta(hours=24)).isoformat()
    if sum(1 for r in rows if (r.get("created_at") or "") >= day_ago) >= OTP_MAX_PER_DAY:
        await log_audit(db, None, "client.otp_failed", "customer", None, norm, {"reason": "daily_cap"}, request)
        return generic

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


def _demo_login() -> Optional[tuple[str, str]]:
    """Opt-in DEMO login for the customer portal — NON-PRODUCTION ONLY.

    Returns (normalized_phone, code) only when BOTH CLIENT_DEMO_PHONE and
    CLIENT_DEMO_OTP are set, letting a single fixed number + code open the portal
    without an SMS gateway (for walkthroughs/demos). It is scoped to that ONE
    seeded number — it is NOT a universal bypass — and is hard-disabled whenever
    APP_ENV=production. Unset by default => no demo login at all.
    """
    if str(os.environ.get("APP_ENV", "")).lower() == "production":
        return None
    phone = normalize_phone(os.environ.get("CLIENT_DEMO_PHONE", ""))
    code = (os.environ.get("CLIENT_DEMO_OTP", "") or "").strip()
    return (phone, code) if phone and code else None


async def _issue_customer_session(norm: str, leads: list[dict], request: Request, demo: bool = False) -> dict:
    """Resolve/create the customer for this phone, link their leads, mint tokens.
    Shared by the real OTP path and the demo path so both behave identically."""
    customer = await _get_or_create_customer(norm, leads)
    for lid in [l["id"] for l in leads]:
        await db.leads.update_one({"id": lid}, {"$set": {"customer_id": customer["id"]}})
    await db.customers.update_one({"id": customer["id"]}, {"$set": {"last_login_at": now_iso()}})
    tv = int(customer.get("token_version") or 0)
    access = create_customer_access_token(customer["id"], customer["phone"], tv=tv)
    refresh = create_customer_refresh_token(customer["id"], tv=tv)
    await log_audit(db, None, "client.login", "customer", customer["id"], customer.get("full_name"),
                    {"phone": norm, **({"demo": True} if demo else {})}, request)
    if demo:
        logger.warning("[DEMO LOGIN] customer portal opened via demo OTP for %s — "
                       "unset CLIENT_DEMO_PHONE/CLIENT_DEMO_OTP before real customer launch", norm)
    customer.pop("_id", None)
    return {"customer": customer, "access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/client/auth/verify-otp")
async def verify_otp(body: VerifyOtpIn, request: Request, _ac: None = Depends(require_app_check)):
    """Step 2 — verify the code and mint a customer session (access + refresh)."""
    invalid = HTTPException(status_code=400, detail="Invalid or expired code")
    norm = normalize_phone(body.phone)
    if not norm:
        raise invalid
    leads = await _leads_for_phone(norm)
    if not leads:
        raise invalid

    # Opt-in demo login (non-production): a fixed phone+code for portal walkthroughs
    # without SMS. Scoped to the one seeded CLIENT_DEMO_PHONE; see _demo_login().
    demo = _demo_login()
    if demo and norm == demo[0] and body.code.strip() == demo[1]:
        return await _issue_customer_session(norm, leads, request, demo=True)

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

    # Success: consume the code, then resolve the customer and mint a session.
    await db.customer_otps.update_one({"id": rec["id"]}, {"$set": {"consumed": True}})
    return await _issue_customer_session(norm, leads, request)


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
    tv = int(customer.get("token_version") or 0)
    if int(payload.get("tv", 0)) != tv:
        raise HTTPException(status_code=401, detail="Session revoked — please sign in again")
    access = create_customer_access_token(customer["id"], customer["phone"], tv=tv)
    return {"access_token": access, "token_type": "bearer"}


@router.post("/client/auth/logout")
async def client_logout(request: Request, customer: dict = Depends(get_current_customer)):
    """Revoke this customer's tokens server-side, then record the event."""
    await revoke_tokens(db.customers, customer["id"])
    await log_audit(db, None, "client.logout", "customer", customer["id"], customer.get("full_name"), None, request)
    return {"ok": True}


@router.post("/client/auth/step-up")
async def client_step_up(request: Request, customer: dict = Depends(get_current_customer)):
    """Issue a short-lived elevation after the app has re-verified the customer
    on-device (biometric/PIN via local_auth). Send the returned token as the
    X-Client-Step-Up header on a high-risk action (accept estimate / approve
    design). Gated actions require it only when CLIENT_STEP_UP_ENABLED."""
    await log_audit(db, None, "client.step_up", "customer", customer["id"], customer.get("full_name"), None, request)
    return {"step_up_token": create_customer_step_up_token(customer["id"]), "expires_in": STEP_UP_TTL_MIN * 60}


@router.get("/client/me")
async def client_me(customer: dict = Depends(get_current_customer)):
    return {"customer": customer}


class DeviceIn(BaseModel):
    token: str
    platform: Optional[str] = None


@router.post("/client/devices")
async def client_register_device(body: DeviceIn, customer: dict = Depends(get_current_customer)):
    """Register this device's FCM token so the customer can receive push notifications."""
    row = await register_device("customer", customer["id"], body.token, body.platform, app="client")
    return {"ok": True, "device_id": row["id"]}


@router.delete("/client/devices")
async def client_unregister_device(body: DeviceIn, customer: dict = Depends(get_current_customer)):
    """Deactivate this device's token (logout / notifications off)."""
    await unregister_device(body.token)
    return {"ok": True}


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
    await assert_client_step_up(request, customer)   # biometric confirm (high-risk)
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


# ---- Designs: view + the customer feedback loop (approve / request changes) ----

class DesignFeedbackIn(BaseModel):
    feedback: str = ""


async def _own_revision_or_404(rev_id: str, customer: dict) -> dict:
    """Load a revision only if it belongs to one of the customer's projects."""
    rev = await db.design_revisions.find_one({"id": rev_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=404, detail="Design not found")
    if rev.get("project_id") not in await _my_project_ids(customer):
        raise HTTPException(status_code=404, detail="Design not found")  # never leak others' designs
    return rev


@router.get("/client/designs")
async def client_designs(customer: dict = Depends(get_current_customer)):
    """The customer's shared design revisions (with any attached render/CAD files)."""
    pids = await _my_project_ids(customer)
    if not pids:
        return {"designs": []}
    revs = await db.design_revisions.find(
        {"project_id": {"$in": pids}, "status": {"$in": CLIENT_VISIBLE_REVISION_STATES}},
        {"_id": 0},
    ).sort("revision_number", -1).to_list(200)
    out = []
    for r in revs:
        linked = await db.documents.find({"linked_revision_id": r["id"]}, {"_id": 0}).to_list(50)
        r["documents"] = [_doc_view(d) for d in linked
                          if not d.get("is_deleted") and d.get("type") in CLIENT_VISIBLE_DOC_TYPES]
        out.append(r)
    return {"designs": out}


@router.post("/client/designs/{rev_id}/approve")
async def client_approve_design(rev_id: str, request: Request,
                                customer: dict = Depends(get_current_customer)):
    """Customer approves a shared design revision (the Production-Design gate needs one)."""
    await assert_client_step_up(request, customer)   # biometric confirm (high-risk)
    rev = await _own_revision_or_404(rev_id, customer)
    if rev["status"] == "Approved":
        return {"ok": True, "revision_id": rev_id, "status": "Approved"}  # idempotent
    if rev["status"] not in ("Shared", "Revision Requested"):
        raise HTTPException(status_code=409, detail="This design is not available to approve")
    ts = now_iso()
    await db.design_revisions.update_one({"id": rev_id}, {"$set": {"status": "Approved"}})
    lead = await db.leads.find_one({"project_id": rev["project_id"]}, {"_id": 0, "id": 1})
    if lead:
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lead["id"], "type": "Note",
            "summary": f"Customer approved design R{rev.get('revision_number')} via the Client App.",
            "actor_id": None, "created_at": ts,
        })
    await log_audit(db, None, "client.design_approved", "revision", rev_id, f"R{rev.get('revision_number')}",
                    {"project_id": rev["project_id"], "channel": "client_app", "customer_id": customer["id"]}, request)
    return {"ok": True, "revision_id": rev_id, "status": "Approved"}


@router.post("/client/designs/{rev_id}/request-changes")
async def client_request_changes(rev_id: str, body: DesignFeedbackIn, request: Request,
                                 customer: dict = Depends(get_current_customer)):
    """Customer asks for design changes; this notifies the designer (same automation
    the CRM uses when an internal user sets 'Revision Requested')."""
    rev = await _own_revision_or_404(rev_id, customer)
    if rev["status"] not in ("Shared", "Approved", "Revision Requested"):
        raise HTTPException(status_code=409, detail="This design is not available for feedback")
    ts = now_iso()
    await db.design_revisions.update_one(
        {"id": rev_id}, {"$set": {"status": "Revision Requested", "client_feedback": body.feedback or ""}})
    new_rev = await db.design_revisions.find_one({"id": rev_id}, {"_id": 0})
    lead = await db.leads.find_one({"project_id": rev["project_id"]}, {"_id": 0, "id": 1})
    if lead:
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lead["id"], "type": "Note",
            "summary": f"Customer requested changes on design R{rev.get('revision_number')} via the Client App.",
            "actor_id": None, "created_at": ts,
        })
    await run_workflow_notify_designer(rev_id, new_rev)
    await log_audit(db, None, "client.design_changes_requested", "revision", rev_id, f"R{rev.get('revision_number')}",
                    {"project_id": rev["project_id"], "channel": "client_app", "customer_id": customer["id"]}, request)
    return {"ok": True, "revision_id": rev_id, "status": "Revision Requested"}


# ---- Payments (history + balance) and Documents (customer-safe files) ----

@router.get("/client/payments")
async def client_payments(customer: dict = Depends(get_current_customer)):
    """The customer's payments (booking + milestones) with a paid/balance summary."""
    pids = await _my_project_ids(customer)
    lead_ids = await _my_lead_ids(customer)
    rows: list[dict] = []
    seen: set[str] = set()
    if pids:
        for p in await db.payments.find({"project_id": {"$in": pids}}, {"_id": 0}).to_list(500):
            if p["id"] not in seen:
                rows.append(p); seen.add(p["id"])
    if lead_ids:  # booking payments are anchored to the lead
        for p in await db.payments.find({"lead_id": {"$in": lead_ids}}, {"_id": 0}).to_list(500):
            if p["id"] not in seen:
                rows.append(p); seen.add(p["id"])

    contract_value = 0.0
    for pid in pids:
        pr = await db.projects.find_one({"id": pid}, {"_id": 0, "contract_value": 1})
        if pr:
            contract_value += (pr.get("contract_value") or 0)
    paid = sum((p.get("amount") or 0) for p in rows if p.get("status") in PAID_PAYMENT_STATES)
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {
        "summary": {
            "contract_value": round(contract_value, 2),
            "paid": round(paid, 2),
            "balance": round(max(contract_value - paid, 0), 2),
            "currency": "INR",
        },
        "payments": [_payment_view(p) for p in rows],
    }


@router.get("/client/documents")
async def client_documents(customer: dict = Depends(get_current_customer)):
    """Customer-appropriate documents only (renders, CAD, design files, quotations,
    site photos) — internal manufacturing docs are never returned."""
    pids = await _my_project_ids(customer)
    if not pids:
        return {"documents": []}
    docs = await db.documents.find({"project_id": {"$in": pids}}, {"_id": 0}).to_list(1000)
    visible = [_doc_view(d) for d in docs
               if not d.get("is_deleted") and d.get("type") in CLIENT_VISIBLE_DOC_TYPES]
    visible.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"documents": visible}


@router.get("/client/documents/{doc_id}/signed-url")
async def client_document_signed_url(doc_id: str, customer: dict = Depends(get_current_customer)):
    """Mint a short-lived signed download URL for a customer-visible document.
    Access is checked here (the doc must belong to one of the customer's projects
    and be a client-visible type); the returned URL is the capability (P1-10)."""
    pids = await _my_project_ids(customer)
    rec = await db.documents.find_one({"id": doc_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not rec or rec.get("project_id") not in pids or rec.get("type") not in CLIENT_VISIBLE_DOC_TYPES:
        raise HTTPException(status_code=404, detail="Not found")
    token = create_doc_download_token(doc_id, customer["id"], "customer")
    return {
        "url": f"/api/documents/download?token={token}",
        "expires_in": DOC_URL_TTL_MIN * 60,
        "filename": safe_filename(rec.get("original_filename")),
    }


# ============================================================================
# <section name="DPDP — consent + data-subject rights (P1-11)">
#   India DPDP Act 2023: consent capture/withdrawal (§6), right to access &
#   data portability (export), and right to erasure (§11-13) via a request the
#   business actions (transactional records are retained per §8(7) retention).
# </section>
CONSENT_PURPOSES = {"data_processing", "marketing", "whatsapp_updates"}
PRIVACY_POLICY_VERSION = "2026-01"


class ConsentIn(BaseModel):
    purpose: str
    granted: bool
    policy_version: Optional[str] = None


class ErasureIn(BaseModel):
    reason: Optional[str] = None


@router.post("/client/me/consent")
async def client_record_consent(body: ConsentIn, request: Request,
                                customer: dict = Depends(get_current_customer)):
    """Record a consent decision (grant or withdraw). Append-only ledger."""
    if body.purpose not in CONSENT_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Unknown purpose. Allowed: {sorted(CONSENT_PURPOSES)}")
    row = {
        "id": str(uuid.uuid4()),
        "subject_type": "customer",
        "subject_id": customer["id"],
        "purpose": body.purpose,
        "policy_version": body.policy_version or PRIVACY_POLICY_VERSION,
        "granted": bool(body.granted),
        "source": "client_app",
        "created_at": now_iso(),
    }
    await db.consents.insert_one(row)
    await log_audit(db, None, "privacy.consent_recorded", "customer", customer["id"], customer.get("full_name"),
                    {"purpose": body.purpose, "granted": bool(body.granted)}, request)
    row.pop("_id", None)
    return row


@router.get("/client/me/consent")
async def client_get_consent(customer: dict = Depends(get_current_customer)):
    """Current consent state (latest decision per purpose) + full history."""
    rows = await db.consents.find({"subject_id": customer["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    current = {}
    for r in rows:  # rows are newest-first, so the first seen per purpose is current
        current.setdefault(r["purpose"], r["granted"])
    return {"policy_version": PRIVACY_POLICY_VERSION, "current": current, "history": rows}


@router.get("/client/me/export")
async def client_export_data(customer: dict = Depends(get_current_customer)):
    """Right to access + data portability: everything we hold about this customer,
    in a structured, customer-safe bundle."""
    lead_ids = await _my_lead_ids(customer)
    pids = await _my_project_ids(customer)
    leads = await db.leads.find({"customer_id": customer["id"]}, {"_id": 0}).to_list(1000)
    projects = await db.projects.find({"id": {"$in": pids}}, {"_id": 0}).to_list(1000) if pids else []
    estimates = await db.estimates.find({"lead_id": {"$in": lead_ids}}, {"_id": 0}).to_list(1000) if lead_ids else []
    payments = await db.payments.find({"project_id": {"$in": pids}}, {"_id": 0}).to_list(1000) if pids else []
    docs = await db.documents.find({"project_id": {"$in": pids}}, {"_id": 0}).to_list(1000) if pids else []
    consents = await db.consents.find({"subject_id": customer["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {
        "generated_at": now_iso(),
        "profile": {k: customer.get(k) for k in ("id", "full_name", "phone", "email", "created_at", "last_login_at")},
        "leads": [{k: l.get(k) for k in ("id", "full_name", "phone", "email", "stage", "status", "created_at")} for l in leads],
        "projects": [{k: p.get(k) for k in ("id", "project_code", "contract_value", "activated_at", "created_at")} for p in projects],
        "estimates": [{k: e.get(k) for k in ("id", "version", "status", "total", "currency", "created_at")} for e in estimates],
        "payments": [_payment_view(p) for p in payments],
        "documents": [_doc_view(d) for d in docs if not d.get("is_deleted") and d.get("type") in CLIENT_VISIBLE_DOC_TYPES],
        "consents": consents,
    }


@router.post("/client/me/erasure-request")
async def client_request_erasure(body: ErasureIn, request: Request,
                                 customer: dict = Depends(get_current_customer)):
    """Right to erasure: lodge a request the business actions. Idempotent — a
    pending request is reused. Actual erasure is a controlled staff step so that
    transactional/tax records can be retained per DPDP §8(7)."""
    existing = await db.erasure_requests.find_one(
        {"customer_id": customer["id"], "status": "pending"}, {"_id": 0})
    if existing:
        return {"ok": True, "status": "pending", "request_id": existing["id"], "message": "An erasure request is already pending."}
    row = {
        "id": str(uuid.uuid4()),
        "customer_id": customer["id"],
        "status": "pending",
        "reason": (body.reason or "")[:500],
        "requested_at": now_iso(),
        "decided_by": None, "decided_at": None, "note": None,
    }
    await db.erasure_requests.insert_one(row)
    await log_audit(db, None, "privacy.erasure_requested", "customer", customer["id"], customer.get("full_name"),
                    {"request_id": row["id"]}, request)
    return {"ok": True, "status": "pending", "request_id": row["id"],
            "message": "Your erasure request has been received. We'll process it per the DPDP Act."}

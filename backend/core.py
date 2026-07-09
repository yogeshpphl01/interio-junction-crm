"""
<module name="core" layer="shared-infrastructure">
  <purpose>
    Single shared module for: the database handle, domain constants, Pydantic
    request schemas, auth dependencies, RBAC visibility helpers, lead-enrichment,
    blueprint stage-gates and automation helpers. Every router imports from here.
  </purpose>
  <storage>
    NOTE: This CRM was migrated from MongoDB to PostgreSQL. `db` is now a
    PostgresDatabase (see database.py) that preserves the exact Motor-style API
    (db.collection.find_one / find / insert_one / update_one / aggregate / ...),
    so all routers below remain unchanged. Connection details come from env
    (DATABASE_URL, or PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD/PG_SSLMODE).
  </storage>
</module>
"""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal, Any

from fastapi import HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr

from auth_utils import decode_token, extract_token
from scoring import compute_score, DEFAULT_WEIGHTS
from database import PostgresDatabase
from pg_schema import LIFECYCLE_PHASES
from permissions import has_permission, require_permission, permissions_for, role_label, role_color

logger = logging.getLogger(__name__)

# ---------- Database (PostgreSQL on Hostinger) ----------
# <db-handle>
#   Built lazily from environment variables. The pool is opened in the FastAPI
#   startup hook (server.py -> db.connect()) and closed on shutdown.
#   `client` is kept as a back-compatible alias of `db`.
# </db-handle>
db = PostgresDatabase.from_env()
client = db

# ---------- Constants ----------
# <pipeline name="9-stage blueprint">
#   The full Interio Junction sales+production pipeline. `id` is the stored
#   integer stage on each lead; `short` is what the Pipeline board / badges show.
#   (Kept in sync with the frontend's lib/constants.js STAGES.)
# </pipeline>
STAGES = [
    {"id": 1, "name": "Leads", "short": "Leads", "color": "#D4A373"},
    {"id": 2, "name": "Initial Estimate", "short": "Initial Estimate", "color": "#C99A4B"},
    {"id": 3, "name": "Consultation", "short": "Consultation", "color": "#8A9A5B"},
    {"id": 4, "name": "Booking", "short": "Booking", "color": "#7C9082"},
    {"id": 5, "name": "Site Measurement", "short": "Site Measurement", "color": "#6B705C"},
    {"id": 6, "name": "Design", "short": "Design", "color": "#9C6644"},
    {"id": 7, "name": "Production Design", "short": "Production Design", "color": "#B0613A"},
    {"id": 8, "name": "Revised Estimate", "short": "Revised Estimate", "color": "#A95A3F"},
    {"id": 9, "name": "Factory Production", "short": "Factory", "color": "#4A5D23"},
]
# Probability a lead at each stage eventually converts (weighted forecast).
STAGE_WIN_RATE = {1: 0.08, 2: 0.16, 3: 0.28, 4: 0.45, 5: 0.55, 6: 0.68, 7: 0.80, 8: 0.90, 9: 1.0}
LEAD_TYPES = ["Retail Client", "Architect", "Interior Designer", "Builder"]
BHK_TYPES = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "Villa"]
KITCHEN_LAYOUTS = ["L-shape", "U-shape", "Parallel", "Straight", "Island"]
LEAD_SOURCES = ["Website", "Referral", "Walk-in", "Instagram", "Facebook", "Architect Partner", "Google", "Other"]
LEAD_STATUSES = ["Active", "Won", "Lost", "On-hold"]
# <constant name="LIFECYCLE_PHASES">
#   Imported from pg_schema (single source of truth). High-level journey buckets
#   exposed to the frontend via /meta so the UI can render/filter by phase.
# </constant>
LEAD_LIFECYCLE_PHASES = LIFECYCLE_PHASES
# Stage at which the project is considered delivered (sent to factory production).
JOURNEY_DELIVERED_STAGE = 9
DOC_TYPES = [
    "Site Measurement Sheet", "2D CAD", "3D Render", "Design File", "Quotation PDF",
    "Cutlist", "BOQ", "BOM", "Site Photo", "Other",
]

ROLE_ADMIN = "admin"
ROLE_SALES = "sales"
ROLE_DESIGNER = "designer"
ROLE_SUPERVISOR = "supervisor"
# <role name="manager">
#   NEW. Uploads campaign lead sheets and assigns leads to the sales team.
#   For lead visibility/operations a manager behaves like an admin (sees all
#   leads), but it is NOT granted user-management / audit / settings access.
# </role>
ROLE_MANAGER = "manager"
# <role name="ceo">
#   Super-admin. Has every admin capability PLUS the authority to hard-DELETE
#   accounts. A CEO account itself can never be deactivated or deleted.
# </role>
ROLE_CEO = "ceo"
# <mobile-hierarchy roles>
#   For the two-app mobile ecosystem (see docs/mobile-apps). Marketing Head ⊇
#   Project Manager (== manager) PLUS ad-campaign Excel upload + silent oversight.
#   Production Engineer ⊇ Designer PLUS factory/cut-list/QR/production. Additive:
#   the existing web-CRM roles are unchanged in behaviour.
# </mobile-hierarchy>
ROLE_MARKETING_HEAD = "marketing_head"
ROLE_PRODUCTION_ENGINEER = "production_engineer"
# Roles with full company-wide lead visibility + admin-equivalent reach.
ADMIN_ROLES = (ROLE_CEO, ROLE_ADMIN)
FULL_VISIBILITY_ROLES = (ROLE_CEO, ROLE_ADMIN, ROLE_MANAGER, ROLE_MARKETING_HEAD)
# Built-in roles. Custom categories (Module 7) are added on top of these.
BUILTIN_ROLES = [ROLE_CEO, ROLE_ADMIN, ROLE_MARKETING_HEAD, ROLE_MANAGER, ROLE_SALES,
                 ROLE_PRODUCTION_ENGINEER, ROLE_DESIGNER, ROLE_SUPERVISOR]

DEFAULT_AUTOMATIONS = [
    {"key": "auto_assign_supervisor", "name": "Auto-assign Site Supervisor", "description": "When a lead enters Site Measurement, auto-assign an available supervisor.", "enabled": True},
    {"key": "sla_breach_48h", "name": "SLA breach (48h idle)", "description": "Flag a lead with no activity for 48 hours.", "enabled": True},
    {"key": "notify_designer_revision", "name": "Notify designer on Revision Requested", "description": "When a revision is set to Revision Requested, notify the designer.", "enabled": True},
    {"key": "escalate_hot_lead", "name": "Escalate untouched Hot lead", "description": "Escalate a Hot lead (score ≥ 80) with no activity in 24h to the manager.", "enabled": True},
]


# ---------- Time helpers ----------
def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def now_iso() -> str:
    return iso(datetime.now(timezone.utc))


# ---------- Pydantic Schemas ----------
class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    # role is validated against the roles table at the endpoint, so any custom
    # category is accepted too (not just the built-in roles).
    email: EmailStr
    full_name: str
    role: str
    phone: Optional[str] = None
    password: Optional[str] = None


class ChangePasswordInput(BaseModel):
    current: str
    new: str


class ProfileUpdate(BaseModel):
    """Self-service personal-detail edit (any logged-in user). Logged to audit."""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    recovery_email: Optional[EmailStr] = None  # personal inbox for reset codes


class ForgotPasswordInput(BaseModel):
    """Step 1 of self-service reset — the account's login email."""
    email: EmailStr


class ResetPasswordInput(BaseModel):
    """Step 2 — the emailed OTP plus the new password."""
    email: EmailStr
    otp: str
    new_password: str


class LeadCreate(BaseModel):
    full_name: str
    email: Optional[EmailStr] = None
    phone: str
    city: Optional[str] = None
    address: Optional[str] = None
    lead_type: str
    source: str
    bhk_type: str
    kitchen_layout: str
    tentative_budget: float = 0
    requirements: Optional[str] = ""
    assigned_to: Optional[str] = None


class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    lead_type: Optional[str] = None
    source: Optional[str] = None
    bhk_type: Optional[str] = None
    kitchen_layout: Optional[str] = None
    tentative_budget: Optional[float] = None
    requirements: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None


class StageMoveInput(BaseModel):
    to_stage: int
    note: Optional[str] = ""
    override: bool = False


class CloseLeadInput(BaseModel):
    status: Literal["Won", "Lost", "On-hold", "Active"]
    reason: Optional[str] = ""
    won_value: Optional[float] = None


class MeasurementInput(BaseModel):
    project_id: str
    scheduled_at: Optional[str] = None
    completed_at: Optional[str] = None
    supervisor_id: Optional[str] = None
    total_area_sqft: Optional[float] = None
    ceiling_height: Optional[float] = None
    status: Optional[str] = "Scheduled"
    notes: Optional[str] = ""


class MeasurementUpdate(BaseModel):
    scheduled_at: Optional[str] = None
    completed_at: Optional[str] = None
    supervisor_id: Optional[str] = None
    total_area_sqft: Optional[float] = None
    ceiling_height: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class RevisionInput(BaseModel):
    project_id: str
    title: str
    designer_id: Optional[str] = None
    status: Optional[str] = "Draft"
    client_feedback: Optional[str] = ""


class RevisionUpdate(BaseModel):
    title: Optional[str] = None
    designer_id: Optional[str] = None
    status: Optional[str] = None
    client_feedback: Optional[str] = None


class PaymentInput(BaseModel):
    project_id: str
    milestone: str
    amount: float
    due_date: Optional[str] = None
    status: Optional[str] = "Pending"


class PaymentUpdate(BaseModel):
    milestone: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    status: Optional[str] = None


class ActivityInput(BaseModel):
    lead_id: str
    type: str
    summary: str


class WeightsInput(BaseModel):
    budget_tier: int = DEFAULT_WEIGHTS["budget_tier"]
    lead_type: int = DEFAULT_WEIGHTS["lead_type"]
    source_quality: int = DEFAULT_WEIGHTS["source_quality"]
    pipeline_progress: int = DEFAULT_WEIGHTS["pipeline_progress"]
    engagement: int = DEFAULT_WEIGHTS["engagement"]
    recency: int = DEFAULT_WEIGHTS["recency"]


class AutomationToggle(BaseModel):
    enabled: bool


class NotificationSettingsInput(BaseModel):
    enabled: bool
    admin_email: Optional[EmailStr] = None
    from_email: Optional[EmailStr] = None
    events: Optional[dict[str, bool]] = None


class TestEmailInput(BaseModel):
    to: EmailStr


# ---------- Auth dependencies ----------
async def get_current_user(request: Request) -> dict:
    token = extract_token(request)
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    user["permissions"] = permissions_for(user["role"])  # for permission-aware UI
    user["role_label"] = role_label(user["role"])         # for badges (incl. custom roles)
    user["role_color"] = role_color(user["role"])
    return user


def require_roles(*roles: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return dep


# ---------- Visibility helpers ----------
async def project_ids_for_designer(user_id: str) -> list[str]:
    cur = db.design_revisions.find({"designer_id": user_id}, {"project_id": 1, "_id": 0})
    return list({d["project_id"] async for d in cur})


async def project_ids_for_supervisor(user_id: str) -> list[str]:
    cur = db.site_measurements.find({"supervisor_id": user_id}, {"project_id": 1, "_id": 0})
    return list({d["project_id"] async for d in cur})


async def visible_lead_ids(user: dict) -> Optional[set[str]]:
    """
    Lead ids the user can see, or None (= all) when they hold 'leads.view_all'.
    Designer/Supervisor keep their special project-linked visibility; everyone
    else (Sales + any custom category without view_all) sees only their own.
    """
    if has_permission(user, "leads.view_all"):
        return None
    if user["role"] == ROLE_DESIGNER:
        pids = await project_ids_for_designer(user["id"])
        if not pids:
            return set()
        lead_docs = await db.leads.find({"project_id": {"$in": pids}}, {"id": 1, "_id": 0}).to_list(10000)
        return {l["id"] for l in lead_docs}
    if user["role"] == ROLE_SUPERVISOR:
        pids = await project_ids_for_supervisor(user["id"])
        if not pids:
            return set()
        lead_docs = await db.leads.find({"project_id": {"$in": pids}}, {"id": 1, "_id": 0}).to_list(10000)
        return {l["id"] for l in lead_docs}
    ids = await db.leads.find({"assigned_to": user["id"]}, {"id": 1, "_id": 0}).to_list(10000)
    return {l["id"] for l in ids}


async def ensure_lead_visible(user: dict, lead: dict) -> None:
    ids = await visible_lead_ids(user)
    if ids is None:
        return
    if lead["id"] not in ids:
        raise HTTPException(status_code=403, detail="Not allowed")


async def ensure_project_visible(user: dict, project_id: str) -> None:
    """Forbid non-admin from touching projects not linked to leads they can access."""
    if user["role"] == ROLE_ADMIN:
        return
    lead = await db.leads.find_one({"project_id": project_id}, {"_id": 0})
    if lead and user["role"] == ROLE_SALES and lead.get("assigned_to") == user["id"]:
        return
    if user["role"] == ROLE_DESIGNER:
        pids = set(await project_ids_for_designer(user["id"]))
        if project_id in pids:
            return
        has_revs = await db.design_revisions.count_documents({"project_id": project_id})
        if has_revs == 0:
            return
    if user["role"] == ROLE_SUPERVISOR:
        pids = set(await project_ids_for_supervisor(user["id"]))
        if project_id in pids:
            return
        has_ms = await db.site_measurements.count_documents({"project_id": project_id})
        if has_ms == 0:
            return
    raise HTTPException(status_code=403, detail="Not allowed for this project")


# ============================================================================
# <section name="Lead journey / lifecycle tracking">
#   <purpose>
#     Track each lead's path through our funnel so we can answer the core
#     business question: did this person ONLY enquire (and never return), did
#     they walk into the MIDDLE of our journey and then not proceed, or did they
#     COMPLETE the whole journey (project delivered)?
#   </purpose>
#   <two-models>
#     1) High-level bucket  -> `lifecycle_phase` (Enquiry / In-Progress /
#        Completed / Dropped / On-hold) + `furthest_stage` reached.
#     2) Granular per-stage -> `journey` (a JSONB list with entered_at/exited_at
#        for every stage) + `dropped_stage` / `dropped_at` / `dropped_reason`.
#   </two-models>
# ============================================================================
def stage_short(stage: int) -> str:
    """Human-readable short label for a pipeline stage id."""
    for s in STAGES:
        if s["id"] == stage:
            return s["short"]
    return f"Stage {stage}"


def derive_lifecycle_phase(stage: int, status: str) -> str:
    """
    <function name="derive_lifecycle_phase">
      Map (stage, status) -> one high-level lifecycle bucket.
      Won or reaching the factory stage = Completed; Lost = Dropped; a brand-new
      Active lead still at stage 1 = Enquiry; anything in between = In-Progress.
    </function>
    """
    if status == "Won" or (status == "Active" and stage >= JOURNEY_DELIVERED_STAGE):
        return "Completed"
    if status == "Lost":
        return "Dropped"
    if status == "On-hold":
        return "On-hold"
    if (stage or 1) <= 1:
        return "Enquiry"
    return "In-Progress"


def _journey_entry(stage: int, ts: str) -> dict:
    """One per-stage record in the journey timeline."""
    return {"stage": stage, "stage_name": stage_short(stage), "entered_at": ts, "exited_at": None}


def init_journey(ts: str) -> list[dict]:
    """Journey for a brand-new lead: it has just entered stage 1 (Captured)."""
    return [_journey_entry(1, ts)]


def record_stage_transition(journey: Optional[list], to_stage: int, ts: str) -> list[dict]:
    """Close the currently-open stage entry and open a new one for `to_stage`."""
    out = [dict(e) for e in (journey or [])]
    for entry in reversed(out):
        if entry.get("exited_at") is None:
            entry["exited_at"] = ts
            break
    out.append(_journey_entry(to_stage, ts))
    return out


def close_open_journey_entry(journey: Optional[list], ts: str) -> list[dict]:
    """Stamp exited_at on the last open entry (used when a lead is Lost/Won)."""
    out = [dict(e) for e in (journey or [])]
    for entry in reversed(out):
        if entry.get("exited_at") is None:
            entry["exited_at"] = ts
            break
    return out


# ---------- Domain helpers ----------
async def enrich_leads(leads: list[dict]) -> list[dict]:
    """Attach owner, project, score + heat to each lead."""
    user_ids = {l.get("assigned_to") for l in leads if l.get("assigned_to")}
    proj_ids = {l.get("project_id") for l in leads if l.get("project_id")}
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": list(user_ids)}}, {"_id": 0, "password_hash": 0})}
    projects = {p["id"]: p async for p in db.projects.find({"id": {"$in": list(proj_ids)}}, {"_id": 0})}
    activity_counts: dict[str, int] = {}
    cur = db.activities.aggregate([
        {"$match": {"lead_id": {"$in": [l["id"] for l in leads]}}},
        {"$group": {"_id": "$lead_id", "count": {"$sum": 1}}},
    ])
    async for row in cur:
        activity_counts[row["_id"]] = row["count"]
    weights_doc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
    weights = weights_doc["value"] if weights_doc else DEFAULT_WEIGHTS
    out = []
    for l in leads:
        owner = users.get(l.get("assigned_to"))
        proj = projects.get(l.get("project_id"))
        score = compute_score(l, activity_counts.get(l["id"], 0), weights)
        out.append({
            **l, "owner": owner, "project": proj,
            "score": score["score"], "heat": score["heat"],
        })
    return out


async def next_project_code() -> str:
    count = await db.projects.count_documents({})
    return f"IJ-{datetime.now(timezone.utc).year}-{(count + 1):04d}"


async def evaluate_gate(lead: dict, to_stage: int) -> tuple[bool, str]:
    """Blueprint stage gates (9-stage pipeline). Returns (allowed, reason_if_blocked).

    Prerequisites are checked when first crossing into the gated stage:
      • Design (6)            -> at least one Site Measurement Completed.
      • Production Design (7) -> at least one Design Revision Approved.
      • Factory Production (9)-> project Booked/Signed-off and >=50% payments Paid.
    """
    proj_id = lead.get("project_id")
    if to_stage >= 6 and lead["stage"] < 6:
        if not proj_id:
            return False, "Project not initialized. Move through Booking / Site Measurement first."
        completed = await db.site_measurements.count_documents({"project_id": proj_id, "status": "Completed"})
        if completed < 1:
            return False, "Blocked: at least one Site Measurement must be marked Completed."
    if to_stage >= 7 and lead["stage"] < 7:
        if not proj_id:
            return False, "Project not initialized."
        approved = await db.design_revisions.count_documents({"project_id": proj_id, "status": "Approved"})
        if approved < 1:
            return False, "Blocked: at least one Design Revision must be marked Approved."
    if to_stage >= 9 and lead["stage"] < 9:
        if not proj_id:
            return False, "Project not initialized."
        proj = await db.projects.find_one({"id": proj_id}, {"_id": 0})
        if not proj or not proj.get("signed_off"):
            return False, "Blocked: project must be Booked / Signed-off first."
        agg = db.payments.aggregate([
            {"$match": {"project_id": proj_id}},
            {"$group": {"_id": "$status", "total": {"$sum": "$amount"}}},
        ])
        sums = {row["_id"]: row["total"] async for row in agg}
        paid = sums.get("Paid", 0)
        total = sum(sums.values())
        if total == 0 or (paid / total) < 0.5:
            return False, f"Blocked: at least 50% of payments must be Paid (currently {round((paid / total) * 100 if total else 0)}%)."
    return True, ""


# ---------- Automation helpers ----------
async def get_automation_state(key: str) -> bool:
    doc = await db.automations.find_one({"key": key}, {"_id": 0})
    if doc is None:
        default = next((a for a in DEFAULT_AUTOMATIONS if a["key"] == key), None)
        return default["enabled"] if default else False
    return doc.get("enabled", False)


async def log_signal(event: str, summary: str, lead_id: Optional[str] = None) -> None:
    await db.automation_signals.insert_one({
        "id": str(uuid.uuid4()),
        "event": event,
        "summary": summary,
        "lead_id": lead_id,
        "created_at": now_iso(),
    })


async def run_workflow_auto_assign_supervisor(lead_id: str, project_id: str) -> None:
    if not await get_automation_state("auto_assign_supervisor"):
        return
    sup = await db.users.find_one({"role": ROLE_SUPERVISOR, "is_active": True}, {"_id": 0})
    if not sup:
        return
    existing = await db.site_measurements.find_one({"project_id": project_id}, {"_id": 0})
    if existing:
        return
    await db.site_measurements.insert_one({
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "scheduled_at": iso(datetime.now(timezone.utc) + timedelta(days=2)),
        "completed_at": None,
        "supervisor_id": sup["id"],
        "total_area_sqft": None,
        "ceiling_height": None,
        "status": "Scheduled",
        "notes": "Auto-scheduled by Interio Junction automation.",
        "created_at": now_iso(),
    })
    await log_signal("auto_assign_supervisor", f"Assigned {sup['full_name']} as supervisor.", lead_id)


async def run_workflow_notify_designer(rev_id: str, rev: dict) -> None:
    if not await get_automation_state("notify_designer_revision"):
        return
    designer = await db.users.find_one({"id": rev.get("designer_id")}, {"_id": 0, "password_hash": 0})
    proj = await db.projects.find_one({"id": rev["project_id"]}, {"_id": 0})
    lead = await db.leads.find_one({"project_id": rev["project_id"]}, {"_id": 0}) if proj else None
    await log_signal(
        "notify_designer_revision",
        f"Notified {designer['full_name'] if designer else 'designer'} — R{rev['revision_number']} requested.",
        lead["id"] if lead else None,
    )
    try:
        from notifications import dispatch_event
        await dispatch_event(db, "notify_designer_revision", lead["id"] if lead else None,
                             {"revision": rev, "designer": designer, "lead": lead})
    except Exception as e:
        logger.warning(f"Notification dispatch failed: {e}")

"""Interio Junction CRM — main FastAPI server."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal, Any

from fastapi import (
    FastAPI, APIRouter, HTTPException, Request, Response, Depends,
    UploadFile, File, Form, Query, Header,
)
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict
import io

from auth_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, decode_token, extract_token,
)
from storage import init_storage, put_object, get_object, APP_NAME
from scoring import compute_score, DEFAULT_WEIGHTS
from seed_data import seed_users, seed_leads

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Mongo
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Interio Junction CRM API")
api = APIRouter(prefix="/api")

# ---------- Constants ----------
STAGES = [
    {"id": 1, "name": "Lead Captured & Qualified", "short": "Captured", "color": "#D4A373"},
    {"id": 2, "name": "Initial Consultation & Rough Estimate", "short": "Consultation", "color": "#8A9A5B"},
    {"id": 3, "name": "Site Measurement Assigned", "short": "Site Measurement", "color": "#6B705C"},
    {"id": 4, "name": "2D/3D Design & Revision Cycle", "short": "Design", "color": "#9C6644"},
    {"id": 5, "name": "Final Quotation & Sign-off", "short": "Quotation", "color": "#A95A3F"},
    {"id": 6, "name": "Sent to Factory Production", "short": "Factory", "color": "#4A5D23"},
]
STAGE_WIN_RATE = {1: 0.10, 2: 0.25, 3: 0.45, 4: 0.65, 5: 0.85, 6: 1.0}
LEAD_TYPES = ["Retail Client", "Architect", "Interior Designer", "Builder"]
BHK_TYPES = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK", "Villa"]
KITCHEN_LAYOUTS = ["L-shape", "U-shape", "Parallel", "Straight", "Island"]
LEAD_SOURCES = ["Website", "Referral", "Walk-in", "Instagram", "Architect Partner", "Google", "Other"]
LEAD_STATUSES = ["Active", "Won", "Lost", "On-hold"]
DOC_TYPES = ["Site Measurement Sheet", "2D CAD", "3D Render", "Quotation PDF", "Site Photo", "Other"]

ROLE_ADMIN = "admin"
ROLE_SALES = "sales"
ROLE_DESIGNER = "designer"
ROLE_SUPERVISOR = "supervisor"


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


# ---------- Pydantic Schemas ----------
class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    phone: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: Literal["admin", "sales", "designer", "supervisor"]
    phone: Optional[str] = None
    password: Optional[str] = None


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


# ---------- Auth ----------
async def get_current_user(request: Request) -> dict:
    token = extract_token(request)
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_roles(*roles: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return dep


def lead_visibility_filter(user: dict) -> dict:
    """Return Mongo filter for which leads this user can see."""
    if user["role"] == ROLE_ADMIN:
        return {}
    if user["role"] == ROLE_SALES:
        return {"assigned_to": user["id"]}
    # Designer / supervisor see leads attached to projects they're working on.
    # Handled per route via joining; default to nothing to be safe.
    return {"$or": [{"assigned_to": user["id"]}, {"id": "__never__"}]}


async def project_ids_for_designer(user_id: str) -> list[str]:
    cur = db.design_revisions.find({"designer_id": user_id}, {"project_id": 1, "_id": 0})
    return list({d["project_id"] async for d in cur})


async def project_ids_for_supervisor(user_id: str) -> list[str]:
    cur = db.site_measurements.find({"supervisor_id": user_id}, {"project_id": 1, "_id": 0})
    return list({d["project_id"] async for d in cur})


async def ensure_project_visible(user: dict, project_id: str) -> None:
    """Forbid non-admin from touching projects not linked to leads they can access."""
    if user["role"] == ROLE_ADMIN:
        return
    # If a lead is attached, defer to lead visibility
    lead = await db.leads.find_one({"project_id": project_id}, {"_id": 0})
    if lead and user["role"] == ROLE_SALES and lead.get("assigned_to") == user["id"]:
        return
    if user["role"] == ROLE_DESIGNER:
        pids = set(await project_ids_for_designer(user["id"]))
        # Allow if the user is creating the first revision on a project that
        # currently has no designer assignment (initial assignment workflow).
        # Otherwise must already be working on it.
        if project_id in pids:
            return
        # Allow if no revisions yet (open project, can pick up)
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


async def visible_lead_ids(user: dict) -> Optional[set[str]]:
    """Return set of lead ids the user can see, or None for admin (all)."""
    if user["role"] == ROLE_ADMIN:
        return None
    if user["role"] == ROLE_SALES:
        ids = await db.leads.find({"assigned_to": user["id"]}, {"id": 1, "_id": 0}).to_list(10000)
        return {l["id"] for l in ids}
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
    return set()


async def ensure_lead_visible(user: dict, lead: dict) -> None:
    ids = await visible_lead_ids(user)
    if ids is None:
        return
    if lead["id"] not in ids:
        raise HTTPException(status_code=403, detail="Not allowed")


# ---------- Health + Meta ----------
@api.get("/")
async def root():
    return {"app": "Interio Junction CRM", "status": "ok"}


@api.get("/meta")
async def meta():
    return {
        "stages": STAGES,
        "lead_types": LEAD_TYPES,
        "bhk_types": BHK_TYPES,
        "kitchen_layouts": KITCHEN_LAYOUTS,
        "lead_sources": LEAD_SOURCES,
        "lead_statuses": LEAD_STATUSES,
        "doc_types": DOC_TYPES,
        "stage_win_rate": STAGE_WIN_RATE,
        "default_weights": DEFAULT_WEIGHTS,
    }


# ---------- Auth Routes ----------
@api.post("/auth/login")
async def login(input: LoginInput, response: Response):
    email = input.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(input.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    user.pop("_id", None)
    user.pop("password_hash", None)
    return {"user": user, "access_token": access, "refresh_token": refresh}


@api.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/refresh")
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


# ---------- Users ----------
@api.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return users


@api.post("/users")
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
        "created_at": _now(),
    }
    await db.users.insert_one(doc)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return doc


@api.patch("/users/{user_id}")
async def update_user(user_id: str, body: dict, admin: dict = Depends(require_roles(ROLE_ADMIN))):
    allowed = {"full_name", "role", "phone", "is_active"}
    update = {k: v for k, v in body.items() if k in allowed}
    if "password" in body and body["password"]:
        update["password_hash"] = hash_password(body["password"])
    if not update:
        return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await db.users.update_one({"id": user_id}, {"$set": update})
    return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})


# ---------- Leads (Kanban cards) ----------
async def enrich_leads(leads: list[dict]) -> list[dict]:
    """Attach owner info, project info, score."""
    user_ids = {l.get("assigned_to") for l in leads if l.get("assigned_to")}
    proj_ids = {l.get("project_id") for l in leads if l.get("project_id")}
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": list(user_ids)}}, {"_id": 0, "password_hash": 0})}
    projects = {p["id"]: p async for p in db.projects.find({"id": {"$in": list(proj_ids)}}, {"_id": 0})}
    # activity counts in one aggregate
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
            **l,
            "owner": owner,
            "project": proj,
            "score": score["score"],
            "heat": score["heat"],
        })
    return out


@api.get("/leads")
async def list_leads(user: dict = Depends(get_current_user), stage: Optional[int] = None, status: Optional[str] = None):
    filt: dict = {}
    if user["role"] == ROLE_ADMIN:
        pass
    elif user["role"] == ROLE_SALES:
        filt["assigned_to"] = user["id"]
    else:
        ids = await visible_lead_ids(user)
        filt["id"] = {"$in": list(ids or [])}
    if stage is not None:
        filt["stage"] = stage
    if status:
        filt["status"] = status
    leads = await db.leads.find(filt, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    return await enrich_leads(leads)


@api.post("/leads")
async def create_lead(payload: LeadCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES):
        raise HTTPException(status_code=403, detail="Only admin/sales can create leads")
    if payload.lead_type not in LEAD_TYPES:
        raise HTTPException(status_code=400, detail="Invalid lead_type")
    if payload.bhk_type not in BHK_TYPES:
        raise HTTPException(status_code=400, detail="Invalid bhk_type")
    if payload.kitchen_layout not in KITCHEN_LAYOUTS:
        raise HTTPException(status_code=400, detail="Invalid kitchen_layout")
    if payload.source not in LEAD_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")
    assigned = payload.assigned_to or user["id"]
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "assigned_to": assigned,
        "created_by": user["id"],
        "stage": 1,
        "status": "Active",
        "project_id": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.leads.insert_one(doc)
    doc.pop("_id", None)
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": doc["id"],
        "type": "Note",
        "summary": f"Lead created from {payload.source}.",
        "actor_id": user["id"],
        "created_at": _now(),
    })
    return (await enrich_leads([doc]))[0]


@api.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    enriched = (await enrich_leads([lead]))[0]
    # attach related data
    project = enriched.get("project")
    measurements = []
    revisions = []
    payments = []
    documents = []
    if project:
        measurements = await db.site_measurements.find({"project_id": project["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
        revisions = await db.design_revisions.find({"project_id": project["id"]}, {"_id": 0}).sort("revision_number", 1).to_list(500)
        payments = await db.payments.find({"project_id": project["id"]}, {"_id": 0}).sort("due_date", 1).to_list(500)
        documents = await db.documents.find({"project_id": project["id"], "is_deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    activities = await db.activities.find({"lead_id": lead_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    stage_history = await db.stage_history.find({"lead_id": lead_id}, {"_id": 0}).sort("created_at", -1).to_list(500)

    # attach actor names to activities & history
    actor_ids = {a.get("actor_id") for a in activities} | {h.get("changed_by") for h in stage_history}
    actor_ids.discard(None)
    actors = {u["id"]: u async for u in db.users.find({"id": {"$in": list(actor_ids)}}, {"_id": 0, "password_hash": 0})}
    for a in activities:
        a["actor"] = actors.get(a.get("actor_id"))
    for h in stage_history:
        h["actor"] = actors.get(h.get("changed_by"))
    # attach designer/supervisor names
    for r in revisions:
        r["designer"] = actors.get(r.get("designer_id")) or await db.users.find_one({"id": r.get("designer_id")}, {"_id": 0, "password_hash": 0})
    for m in measurements:
        m["supervisor"] = actors.get(m.get("supervisor_id")) or await db.users.find_one({"id": m.get("supervisor_id")}, {"_id": 0, "password_hash": 0})

    return {
        **enriched,
        "measurements": measurements,
        "revisions": revisions,
        "payments": payments,
        "documents": documents,
        "activities": activities,
        "stage_history": stage_history,
    }


@api.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES):
        raise HTTPException(status_code=403, detail="Only admin/sales can edit leads")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    update["updated_at"] = _now()
    await db.leads.update_one({"id": lead_id}, {"$set": update})
    new_lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    return (await enrich_leads([new_lead]))[0]


async def next_project_code() -> str:
    count = await db.projects.count_documents({})
    return f"IJ-{datetime.now(timezone.utc).year}-{(count + 1):04d}"


async def evaluate_gate(lead: dict, to_stage: int) -> tuple[bool, str]:
    """Blueprint gates. Returns (allowed, reason_if_blocked)."""
    proj_id = lead.get("project_id")
    # 3->4 requires measurement Completed
    if to_stage >= 4 and lead["stage"] < 4:
        if not proj_id:
            return False, "Project not initialized. Move through Site Measurement first."
        completed = await db.site_measurements.count_documents({"project_id": proj_id, "status": "Completed"})
        if completed < 1:
            return False, "Blocked: at least one Site Measurement must be marked Completed."
    # 4->5 requires ≥1 revision Approved
    if to_stage >= 5 and lead["stage"] < 5:
        if not proj_id:
            return False, "Project not initialized."
        approved = await db.design_revisions.count_documents({"project_id": proj_id, "status": "Approved"})
        if approved < 1:
            return False, "Blocked: at least one Design Revision must be marked Approved."
    # 5->6 requires sign-off + ≥50% payments paid
    if to_stage >= 6 and lead["stage"] < 6:
        if not proj_id:
            return False, "Project not initialized."
        proj = await db.projects.find_one({"id": proj_id}, {"_id": 0})
        if not proj or not proj.get("signed_off"):
            return False, "Blocked: project must be Signed-off (Quotation stage)."
        # sum payments
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


@api.post("/leads/{lead_id}/move")
async def move_lead(lead_id: str, payload: StageMoveInput, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES):
        raise HTTPException(status_code=403, detail="Only admin/sales can move leads")
    await ensure_lead_visible(user, lead)
    to = int(payload.to_stage)
    if to < 1 or to > 6:
        raise HTTPException(status_code=400, detail="Invalid stage")
    if to == lead["stage"]:
        return (await enrich_leads([lead]))[0]
    allowed, reason = await evaluate_gate(lead, to)
    if not allowed and not (payload.override and user["role"] == ROLE_ADMIN):
        raise HTTPException(status_code=409, detail=reason)

    from_stage = lead["stage"]
    update: dict[str, Any] = {"stage": to, "updated_at": _now()}

    # Auto-create project on first reach of Site Measurement (stage 3)
    if to >= 3 and not lead.get("project_id"):
        code = await next_project_code()
        proj_doc = {
            "id": str(uuid.uuid4()),
            "project_code": code,
            "lead_id": lead_id,
            "rough_estimate": lead.get("tentative_budget", 0),
            "contract_value": None,
            "signed_off": False,
            "sent_to_factory": False,
            "factory_handover_at": None,
            "created_at": _now(),
        }
        await db.projects.insert_one(proj_doc)
        update["project_id"] = proj_doc["id"]
        # workflow rule: auto-assign supervisor if entering stage 3
        await run_workflow_auto_assign_supervisor(lead_id, proj_doc["id"])

    if to >= 5 and from_stage < 5 and lead.get("project_id"):
        await db.projects.update_one({"id": lead["project_id"]}, {"$set": {"signed_off": True, "contract_value": lead.get("tentative_budget")}})
    if to >= 6 and from_stage < 6 and lead.get("project_id"):
        await db.projects.update_one({"id": lead["project_id"]}, {"$set": {"sent_to_factory": True, "factory_handover_at": _now()}})

    await db.leads.update_one({"id": lead_id}, {"$set": update})

    await db.stage_history.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "from_stage": from_stage,
        "to_stage": to,
        "changed_by": user["id"],
        "note": payload.note or "",
        "created_at": _now(),
    })
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "type": "Stage Change",
        "summary": f"Moved from {STAGES[from_stage-1]['short']} → {STAGES[to-1]['short']}.",
        "actor_id": user["id"],
        "created_at": _now(),
    })
    new_lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    return (await enrich_leads([new_lead]))[0]


@api.post("/leads/{lead_id}/check-gate")
async def check_gate(lead_id: str, payload: StageMoveInput, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    allowed, reason = await evaluate_gate(lead, int(payload.to_stage))
    return {"allowed": allowed, "reason": reason}


# ---------- Measurements ----------
@api.post("/measurements")
async def create_measurement(payload: MeasurementInput, user: dict = Depends(get_current_user)):
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_SUPERVISOR):
        raise HTTPException(status_code=403, detail="Forbidden")
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, payload.project_id)
    supervisor_id = payload.supervisor_id
    if user["role"] == ROLE_SUPERVISOR:
        supervisor_id = user["id"]
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "supervisor_id": supervisor_id,
        "created_at": _now(),
    }
    await db.site_measurements.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/measurements/{ms_id}")
async def update_measurement(ms_id: str, payload: MeasurementUpdate, user: dict = Depends(get_current_user)):
    ms = await db.site_measurements.find_one({"id": ms_id}, {"_id": 0})
    if not ms:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == ROLE_SUPERVISOR and ms.get("supervisor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your measurement")
    if user["role"] in (ROLE_DESIGNER,):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    await db.site_measurements.update_one({"id": ms_id}, {"$set": update})
    return await db.site_measurements.find_one({"id": ms_id}, {"_id": 0})


@api.get("/measurements")
async def list_measurements(user: dict = Depends(get_current_user)):
    filt: dict = {}
    if user["role"] == ROLE_SUPERVISOR:
        filt["supervisor_id"] = user["id"]
    elif user["role"] == ROLE_DESIGNER:
        pids = await project_ids_for_designer(user["id"])
        filt["project_id"] = {"$in": pids}
    elif user["role"] == ROLE_SALES:
        # only measurements of projects of leads assigned to this sales person
        lead_docs = await db.leads.find({"assigned_to": user["id"], "project_id": {"$ne": None}}, {"project_id": 1, "_id": 0}).to_list(5000)
        filt["project_id"] = {"$in": [l["project_id"] for l in lead_docs]}
    measurements = await db.site_measurements.find(filt, {"_id": 0}).sort("scheduled_at", -1).to_list(1000)
    # attach project_code + lead name + supervisor name
    proj_ids = list({m["project_id"] for m in measurements})
    sup_ids = list({m.get("supervisor_id") for m in measurements if m.get("supervisor_id")})
    projs = {p["id"]: p async for p in db.projects.find({"id": {"$in": proj_ids}}, {"_id": 0})}
    lead_ids = [p["lead_id"] for p in projs.values()]
    leads = {l["id"]: l async for l in db.leads.find({"id": {"$in": lead_ids}}, {"_id": 0})}
    sups = {u["id"]: u async for u in db.users.find({"id": {"$in": sup_ids}}, {"_id": 0, "password_hash": 0})}
    for m in measurements:
        p = projs.get(m["project_id"])
        m["project"] = p
        m["lead"] = leads.get(p["lead_id"]) if p else None
        m["supervisor"] = sups.get(m.get("supervisor_id"))
    return measurements


# ---------- Revisions ----------
@api.post("/revisions")
async def create_revision(payload: RevisionInput, user: dict = Depends(get_current_user)):
    if user["role"] not in (ROLE_ADMIN, ROLE_SALES, ROLE_DESIGNER):
        raise HTTPException(status_code=403, detail="Forbidden")
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, payload.project_id)
    designer_id = payload.designer_id
    if user["role"] == ROLE_DESIGNER:
        designer_id = user["id"]
    last = await db.design_revisions.find({"project_id": payload.project_id}, {"revision_number": 1, "_id": 0}).sort("revision_number", -1).limit(1).to_list(1)
    next_num = (last[0]["revision_number"] + 1) if last else 1
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": payload.project_id,
        "revision_number": next_num,
        "title": payload.title,
        "designer_id": designer_id,
        "status": payload.status or "Draft",
        "client_feedback": payload.client_feedback or "",
        "created_at": _now(),
    }
    await db.design_revisions.insert_one(doc)
    # activity on the lead
    lead = await db.leads.find_one({"project_id": payload.project_id}, {"id": 1, "_id": 0})
    if lead:
        await db.activities.insert_one({
            "id": str(uuid.uuid4()),
            "lead_id": lead["id"],
            "type": "Note",
            "summary": f"Design Revision R{next_num} created.",
            "actor_id": user["id"],
            "created_at": _now(),
        })
    doc.pop("_id", None)
    return doc


@api.patch("/revisions/{rev_id}")
async def update_revision(rev_id: str, payload: RevisionUpdate, user: dict = Depends(get_current_user)):
    rev = await db.design_revisions.find_one({"id": rev_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == ROLE_SUPERVISOR:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == ROLE_DESIGNER and rev.get("designer_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your revision")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    await db.design_revisions.update_one({"id": rev_id}, {"$set": update})
    new_rev = await db.design_revisions.find_one({"id": rev_id}, {"_id": 0})
    # Workflow: notify designer when status set to Revision Requested
    if payload.status == "Revision Requested":
        await run_workflow_notify_designer(rev_id, new_rev)
    return new_rev


# ---------- Payments ----------
@api.post("/payments")
async def create_payment(payload: PaymentInput, user: dict = Depends(require_roles(ROLE_ADMIN, ROLE_SALES))):
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "paid_date": None,
        "created_at": _now(),
    }
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/payments/{pid}")
async def update_payment(pid: str, payload: PaymentUpdate, user: dict = Depends(require_roles(ROLE_ADMIN, ROLE_SALES))):
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if update.get("status") == "Paid" and not update.get("paid_date"):
        update["paid_date"] = _now()
    await db.payments.update_one({"id": pid}, {"$set": update})
    return await db.payments.find_one({"id": pid}, {"_id": 0})


# ---------- Activities ----------
@api.post("/activities")
async def add_activity(payload: ActivityInput, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": payload.lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    doc = {
        "id": str(uuid.uuid4()),
        "lead_id": payload.lead_id,
        "type": payload.type,
        "summary": payload.summary,
        "actor_id": user["id"],
        "created_at": _now(),
    }
    await db.activities.insert_one(doc)
    await db.leads.update_one({"id": payload.lead_id}, {"$set": {"updated_at": _now()}})
    doc.pop("_id", None)
    doc["actor"] = user
    return doc


# ---------- Documents (uploads) ----------
@api.post("/documents")
async def upload_document(
    project_id: str = Form(...),
    type: str = Form(...),
    linked_measurement_id: Optional[str] = Form(None),
    linked_revision_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, project_id)
    # Role rules: designers can upload 2D CAD / 3D Render; supervisors can upload Site Measurement Sheet / Site Photo
    if user["role"] == ROLE_DESIGNER and type not in ("2D CAD", "3D Render", "Quotation PDF", "Other"):
        raise HTTPException(status_code=403, detail="Designers can upload only design files")
    if user["role"] == ROLE_SUPERVISOR and type not in ("Site Measurement Sheet", "Site Photo", "Other"):
        raise HTTPException(status_code=403, detail="Supervisors can upload only site files")
    if type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Invalid document type")

    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")
    ext = (file.filename or "file").split(".")[-1] if "." in (file.filename or "") else "bin"
    path = f"{APP_NAME}/projects/{project_id}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, content, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "type": type,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(content)),
        "uploaded_by": user["id"],
        "linked_measurement_id": linked_measurement_id,
        "linked_revision_id": linked_revision_id,
        "is_deleted": False,
        "created_at": _now(),
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, user: dict = Depends(get_current_user)):
    rec = await db.documents.find_one({"id": doc_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    # Access control: user must have access to the project (via lead visibility)
    lead = await db.leads.find_one({"project_id": rec["project_id"]}, {"_id": 0})
    if lead:
        await ensure_lead_visible(user, lead)
    try:
        data, _ct = get_object(rec["storage_path"])
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail="Download failed")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=rec.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{rec.get("original_filename","file")}"'},
    )


# ---------- Scoring ----------
@api.get("/scoring")
async def list_scoring(user: dict = Depends(get_current_user), weights: Optional[str] = None):
    """Return all visible leads ranked by score with full signal breakdown."""
    filt: dict = {}
    if user["role"] == ROLE_ADMIN:
        pass
    elif user["role"] == ROLE_SALES:
        filt["assigned_to"] = user["id"]
    else:
        ids = await visible_lead_ids(user)
        filt["id"] = {"$in": list(ids or [])}

    weights_dict = DEFAULT_WEIGHTS.copy()
    if weights:
        import json
        try:
            override = json.loads(weights)
            for k in DEFAULT_WEIGHTS:
                if k in override:
                    weights_dict[k] = int(override[k])
        except Exception:
            pass
    else:
        wdoc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
        if wdoc:
            weights_dict = wdoc["value"]

    leads = await db.leads.find(filt, {"_id": 0}).to_list(2000)
    # activity counts
    activity_counts: dict[str, int] = {}
    cur = db.activities.aggregate([
        {"$match": {"lead_id": {"$in": [l["id"] for l in leads]}}},
        {"$group": {"_id": "$lead_id", "count": {"$sum": 1}}},
    ])
    async for row in cur:
        activity_counts[row["_id"]] = row["count"]

    enriched = []
    for l in leads:
        s = compute_score(l, activity_counts.get(l["id"], 0), weights_dict)
        enriched.append({
            "lead_id": l["id"],
            "full_name": l["full_name"],
            "lead_type": l["lead_type"],
            "stage": l["stage"],
            "tentative_budget": l["tentative_budget"],
            "score": s["score"],
            "heat": s["heat"],
            "signals": s["signals"],
        })
    enriched.sort(key=lambda x: x["score"], reverse=True)
    return {"weights": weights_dict, "leads": enriched}


@api.post("/scoring/weights")
async def save_weights(payload: WeightsInput, user: dict = Depends(require_roles(ROLE_ADMIN))):
    w = payload.model_dump()
    await db.settings.update_one({"key": "score_weights"}, {"$set": {"value": w}}, upsert=True)
    return {"weights": w}


@api.get("/scoring/weights")
async def get_weights(user: dict = Depends(get_current_user)):
    wdoc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
    return {"weights": wdoc["value"] if wdoc else DEFAULT_WEIGHTS}


# ---------- Automations ----------
DEFAULT_AUTOMATIONS = [
    {"key": "auto_assign_supervisor", "name": "Auto-assign Site Supervisor", "description": "When a lead enters Site Measurement, auto-assign an available supervisor.", "enabled": True},
    {"key": "sla_breach_48h", "name": "SLA breach (48h idle)", "description": "Flag a lead with no activity for 48 hours.", "enabled": True},
    {"key": "notify_designer_revision", "name": "Notify designer on Revision Requested", "description": "When a revision is set to Revision Requested, notify the designer.", "enabled": True},
    {"key": "escalate_hot_lead", "name": "Escalate untouched Hot lead", "description": "Escalate a Hot lead (score ≥ 80) with no activity in 24h to the manager.", "enabled": True},
]


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
        "created_at": _now(),
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
        "scheduled_at": _iso(datetime.now(timezone.utc) + timedelta(days=2)),
        "completed_at": None,
        "supervisor_id": sup["id"],
        "total_area_sqft": None,
        "ceiling_height": None,
        "status": "Scheduled",
        "notes": "Auto-scheduled by Interio Junction automation.",
        "created_at": _now(),
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


@api.get("/automations")
async def list_automations(user: dict = Depends(get_current_user)):
    out = []
    for a in DEFAULT_AUTOMATIONS:
        doc = await db.automations.find_one({"key": a["key"]}, {"_id": 0})
        enabled = doc.get("enabled", a["enabled"]) if doc else a["enabled"]
        # runs today
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        runs = await db.automation_signals.count_documents({"event": a["key"], "created_at": {"$gte": today}})
        out.append({**a, "enabled": enabled, "runs_today": runs})
    return out


@api.patch("/automations/{key}")
async def toggle_automation(key: str, payload: AutomationToggle, user: dict = Depends(require_roles(ROLE_ADMIN))):
    if not any(a["key"] == key for a in DEFAULT_AUTOMATIONS):
        raise HTTPException(status_code=404, detail="Unknown automation")
    await db.automations.update_one({"key": key}, {"$set": {"enabled": payload.enabled}}, upsert=True)
    return {"key": key, "enabled": payload.enabled}


@api.post("/automations/run-checks")
async def run_checks(user: dict = Depends(get_current_user)):
    """Run idle-based checks (SLA 48h, escalate hot 24h). Idempotent-ish: latest signal per lead per day."""
    now = datetime.now(timezone.utc)
    cutoff_48 = (now - timedelta(hours=48)).isoformat()
    cutoff_24 = (now - timedelta(hours=24)).isoformat()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    fired = 0

    if await get_automation_state("sla_breach_48h"):
        # leads idle (updated_at <= 48h ago) and Active
        leads = await db.leads.find({"updated_at": {"$lte": cutoff_48}, "status": "Active"}, {"_id": 0}).to_list(500)
        for l in leads:
            existing = await db.automation_signals.find_one({"event": "sla_breach_48h", "lead_id": l["id"], "created_at": {"$gte": today}})
            if existing:
                continue
            await log_signal("sla_breach_48h", f"SLA breach — {l['full_name']} idle 48h.", l["id"])
            fired += 1

    if await get_automation_state("escalate_hot_lead"):
        wdoc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
        weights = wdoc["value"] if wdoc else DEFAULT_WEIGHTS
        leads = await db.leads.find({"status": "Active"}, {"_id": 0}).to_list(2000)
        counts_cur = db.activities.aggregate([
            {"$group": {"_id": "$lead_id", "count": {"$sum": 1}}}
        ])
        counts = {row["_id"]: row["count"] async for row in counts_cur}
        for l in leads:
            s = compute_score(l, counts.get(l["id"], 0), weights)
            if s["score"] >= 80 and l.get("updated_at", "") <= cutoff_24:
                existing = await db.automation_signals.find_one({"event": "escalate_hot_lead", "lead_id": l["id"], "created_at": {"$gte": today}})
                if existing:
                    continue
                await log_signal("escalate_hot_lead", f"Escalated Hot lead {l['full_name']} (score {s['score']}).", l["id"])
                fired += 1

    return {"fired": fired}


@api.get("/automations/signals")
async def signals(user: dict = Depends(get_current_user), limit: int = 50):
    rows = await db.automation_signals.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return rows


# ---------- Analytics ----------
@api.get("/analytics/command-center")
async def command_center(user: dict = Depends(get_current_user)):
    filt: dict = {}
    if user["role"] == ROLE_ADMIN:
        scope = "company"
    elif user["role"] == ROLE_SALES:
        filt["assigned_to"] = user["id"]
        scope = "self"
    else:
        ids = await visible_lead_ids(user)
        filt["id"] = {"$in": list(ids or [])}
        scope = "self"

    leads = await db.leads.find(filt, {"_id": 0}).to_list(5000)
    total_pipeline = sum(l.get("tentative_budget", 0) for l in leads if l.get("status") == "Active")
    forecast = sum(l.get("tentative_budget", 0) * STAGE_WIN_RATE.get(l.get("stage", 1), 0) for l in leads if l.get("status") == "Active")
    won = [l for l in leads if l.get("status") == "Won"]
    closed = [l for l in leads if l.get("status") in ("Won", "Lost")]
    win_rate = (len(won) / len(closed) * 100) if closed else 0

    # cycle time (Won leads)
    cycle_days = 0
    if won:
        diffs = []
        for l in won:
            try:
                c = datetime.fromisoformat(l["created_at"])
                u = datetime.fromisoformat(l["updated_at"])
                diffs.append((u - c).total_seconds() / 86400)
            except Exception:
                pass
        cycle_days = sum(diffs) / len(diffs) if diffs else 0

    # funnel
    funnel = []
    for s in STAGES:
        items = [l for l in leads if l.get("stage") == s["id"] and l.get("status") == "Active"]
        funnel.append({
            "stage": s["id"],
            "name": s["short"],
            "color": s["color"],
            "count": len(items),
            "value": sum(l.get("tentative_budget", 0) for l in items),
        })

    by_source: dict[str, float] = {}
    for l in leads:
        if l.get("status") == "Active":
            by_source[l.get("source", "Other")] = by_source.get(l.get("source", "Other"), 0) + l.get("tentative_budget", 0)
    sources = [{"source": k, "value": v} for k, v in by_source.items()]
    sources.sort(key=lambda x: x["value"], reverse=True)

    # forecast trend (next 6 months, simple projection per stage probability over time)
    months = []
    now = datetime.now(timezone.utc)
    for i in range(6):
        m = now + timedelta(days=30 * i)
        # spread forecast as it ramps to 100% as stages progress; simple linear allocation
        ratio = (i + 1) / 6
        months.append({
            "month": m.strftime("%b %Y"),
            "forecast": round(forecast * ratio, 2),
            "pipeline": round(total_pipeline * (1 - ratio * 0.3), 2),
        })

    return {
        "scope": scope,
        "kpis": {
            "total_pipeline": total_pipeline,
            "forecast": round(forecast, 2),
            "win_rate": round(win_rate, 1),
            "cycle_days": round(cycle_days, 1),
            "active_leads": len([l for l in leads if l.get("status") == "Active"]),
            "won_count": len(won),
        },
        "funnel": funnel,
        "by_source": sources,
        "forecast_trend": months,
    }


# ---------- Startup ----------
@app.on_event("startup")
async def on_startup():
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.leads.create_index("id", unique=True)
    await db.leads.create_index("stage")
    await db.leads.create_index("assigned_to")
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("project_code", unique=True)
    await db.design_revisions.create_index([("project_id", 1), ("revision_number", 1)], unique=True)
    await db.activities.create_index("lead_id")
    await db.stage_history.create_index("lead_id")
    await db.documents.create_index("project_id")
    await db.settings.create_index("key", unique=True)
    await db.automations.create_index("key", unique=True)

    # Storage
    try:
        init_storage()
    except Exception as e:
        logger.error(f"Storage init error: {e}")

    # Seed
    email_to_id = await seed_users(db)
    await seed_leads(db, email_to_id)

    # Default automations state
    for a in DEFAULT_AUTOMATIONS:
        if not await db.automations.find_one({"key": a["key"]}):
            await db.automations.insert_one({"key": a["key"], "enabled": a["enabled"]})


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)

# CORS — credentials + explicit origin
origins_env = os.environ.get("CORS_ORIGINS", "*")
if origins_env == "*":
    cors_origins = ["*"]
    allow_creds = False
else:
    cors_origins = [o.strip() for o in origins_env.split(",")]
    allow_creds = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

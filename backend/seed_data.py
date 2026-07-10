"""Seed users and sample leads so every screen is populated on first run."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from auth_utils import hash_password

logger = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


# <journey-seed>
#   Short stage labels + a builder for the per-stage journey timeline, so seeded
#   leads carry the same lifecycle/journey data that live leads accrue.
# </journey-seed>
STAGE_SHORT = {
    1: "Leads", 2: "Initial Estimate", 3: "Consultation", 4: "Booking", 5: "Site Measurement",
    6: "Design", 7: "Production Design", 8: "Revised Estimate", 9: "Factory",
}


def _seed_journey(created: datetime, current_stage: int) -> list[dict]:
    """Build a plausible stage-by-stage journey for a seeded lead."""
    out = []
    for s in range(1, current_stage + 1):
        out.append({
            "stage": s,
            "stage_name": STAGE_SHORT.get(s, f"Stage {s}"),
            "entered_at": _iso(created + timedelta(days=s - 1)),
            "exited_at": _iso(created + timedelta(days=s)) if s < current_stage else None,
        })
    return out


def _seed_lifecycle(stage: int) -> str:
    if stage >= 9:
        return "Completed"
    if stage >= 2:
        return "In-Progress"
    return "Enquiry"


SEED_USERS = [
    {
        # <ceo>Super-account — full authority incl. hard-delete; cannot itself be
        #   deactivated or deleted. Initial password = ADMIN_PASSWORD env.</ceo>
        "email": os.environ.get("CEO_EMAIL", "ceo@interiojunction.com"),
        "full_name": "Yogesh Pophale",
        "role": "ceo",
        "phone": os.environ.get("CEO_PHONE", ""),
    },
    {
        # <tester>A second super-account with the SAME capabilities as the CEO
        #   (role "ceo"), for QA/testing. Initial password = ADMIN_PASSWORD; can
        #   sign in directly (no forced password change).</tester>
        "email": os.environ.get("TESTER_EMAIL", "tester@interiojunction.com"),
        "full_name": "Tester",
        "role": "ceo",
        "phone": "",
        "must_change": False,
    },
    {
        "email": os.environ.get("ADMIN_EMAIL", "admin@interiojunction.com"),
        "full_name": "Aanya Mehra",
        "role": "admin",
        "phone": "+91 98220 11001",
    },
    {
        "email": "sales@interiojunction.com",
        "full_name": "Rohan Kapoor",
        "role": "sales",
        "phone": "+91 98220 22002",
    },
    {
        "email": "designer@interiojunction.com",
        "full_name": "Ishita Bose",
        "role": "designer",
        "phone": "+91 98220 33003",
    },
    {
        "email": "supervisor@interiojunction.com",
        "full_name": "Vikram Shetty",
        "role": "supervisor",
        "phone": "+91 98220 44004",
    },
]


async def seed_users(db) -> dict[str, str]:
    """Idempotent user seeding. Returns email->id map."""
    default_pwd = os.environ.get("DEFAULT_USER_PASSWORD", "interio2026")
    admin_pwd = os.environ.get("ADMIN_PASSWORD", default_pwd)
    email_to_id: dict[str, str] = {}
    for u in SEED_USERS:
        existing = await db.users.find_one({"email": u["email"]})
        pwd = admin_pwd if u["role"] in ("admin", "ceo") else default_pwd
        if existing:
            email_to_id[u["email"]] = existing["id"]
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "email": u["email"],
            "password_hash": hash_password(pwd),
            "full_name": u["full_name"],
            "role": u["role"],
            "phone": u["phone"],
            "is_active": True,
            # CEO sets own password on first login; per-user override (e.g. Tester) wins.
            "must_change_password": u.get("must_change", u["role"] == "ceo"),
            "created_at": _iso(datetime.now(timezone.utc)),
        }
        await db.users.insert_one(doc)
        email_to_id[u["email"]] = doc["id"]
    logger.info(f"Seeded users: {list(email_to_id.keys())}")
    return email_to_id


# 8 sample leads spread across the 6 stages.
SAMPLE_LEADS = [
    {
        "full_name": "Anjali Sharma",
        "email": "anjali.sharma@example.com",
        "phone": "+91 98765 11111",
        "city": "Pune",
        "address": "Kalyani Nagar",
        "lead_type": "Retail Client",
        "source": "Website",
        "bhk_type": "3 BHK",
        "kitchen_layout": "L-shape",
        "tentative_budget": 850000,
        "requirements": "Full home interiors with modular kitchen and 2 wardrobes.",
        "stage": 1,
    },
    {
        "full_name": "Studio Aakar (Meera Iyer)",
        "email": "meera@studioaakar.in",
        "phone": "+91 98765 22222",
        "city": "Mumbai",
        "address": "Bandra West",
        "lead_type": "Architect",
        "source": "Architect Partner",
        "bhk_type": "Villa",
        "kitchen_layout": "Island",
        "tentative_budget": 6500000,
        "requirements": "Premium villa interior; full carpentry, ceiling, modular kitchen.",
        "stage": 2,
    },
    {
        "full_name": "Rahul Verma",
        "email": "rahul.verma@example.com",
        "phone": "+91 98765 33333",
        "city": "Bengaluru",
        "address": "Whitefield",
        "lead_type": "Retail Client",
        "source": "Instagram",
        "bhk_type": "2 BHK",
        "kitchen_layout": "Parallel",
        "tentative_budget": 550000,
        "requirements": "Modular kitchen + master wardrobe.",
        "stage": 4,
    },
    {
        "full_name": "Sneha Patel",
        "email": "sneha.patel@example.com",
        "phone": "+91 98765 44444",
        "city": "Ahmedabad",
        "address": "Bodakdev",
        "lead_type": "Interior Designer",
        "source": "Referral",
        "bhk_type": "4 BHK",
        "kitchen_layout": "U-shape",
        "tentative_budget": 2800000,
        "requirements": "Client handover; full carpentry package.",
        "stage": 5,
    },
    {
        "full_name": "Kunal Bansal",
        "email": "kunal.b@example.com",
        "phone": "+91 98765 55555",
        "city": "Gurugram",
        "address": "Golf Course Road",
        "lead_type": "Retail Client",
        "source": "Google",
        "bhk_type": "3 BHK",
        "kitchen_layout": "L-shape",
        "tentative_budget": 1200000,
        "requirements": "Kitchen + wardrobes + TV unit.",
        "stage": 6,
    },
    {
        "full_name": "Lalit Builders Pvt Ltd",
        "email": "projects@lalitbuilders.com",
        "phone": "+91 98765 66666",
        "city": "Pune",
        "address": "Baner",
        "lead_type": "Builder",
        "source": "Referral",
        "bhk_type": "2 BHK",
        "kitchen_layout": "Straight",
        "tentative_budget": 4200000,
        "requirements": "16-unit interior package for new tower.",
        "stage": 7,
    },
    {
        "full_name": "Priya Nair",
        "email": "priya.nair@example.com",
        "phone": "+91 98765 77777",
        "city": "Kochi",
        "address": "Panampilly Nagar",
        "lead_type": "Retail Client",
        "source": "Website",
        "bhk_type": "3 BHK",
        "kitchen_layout": "U-shape",
        "tentative_budget": 1850000,
        "requirements": "Revised quotation pending; signoff in 2 days.",
        "stage": 8,
    },
    {
        "full_name": "Ahuja Residence",
        "email": "rajeev.ahuja@example.com",
        "phone": "+91 98765 88888",
        "city": "Delhi",
        "address": "Greater Kailash II",
        "lead_type": "Retail Client",
        "source": "Architect Partner",
        "bhk_type": "4 BHK",
        "kitchen_layout": "Island",
        "tentative_budget": 3600000,
        "requirements": "Sent to factory; awaiting handover schedule.",
        "stage": 9,
    },
]


async def seed_leads(db, email_to_id: dict[str, str]) -> None:
    if await db.leads.count_documents({}) > 0:
        return
    sales_id = email_to_id.get("sales@interiojunction.com")
    designer_id = email_to_id.get("designer@interiojunction.com")
    supervisor_id = email_to_id.get("supervisor@interiojunction.com")
    admin_id = email_to_id.get(os.environ.get("ADMIN_EMAIL", "admin@interiojunction.com"))
    now = datetime.now(timezone.utc)

    project_counter = 1
    for i, lead in enumerate(SAMPLE_LEADS):
        lead_id = str(uuid.uuid4())
        created = now - timedelta(days=20 - i, hours=i * 3)
        updated = now - timedelta(hours=(i + 1) * 4)
        # Assign all to sales; admin can see all anyway
        doc = {
            "id": lead_id,
            **lead,
            "status": "Active",
            "assigned_to": sales_id,
            "created_by": admin_id,
            "project_id": None,
            # <journey-fields>seed the lifecycle bucket + per-stage timeline</journey-fields>
            "lifecycle_phase": _seed_lifecycle(lead["stage"]),
            "furthest_stage": lead["stage"],
            "journey": _seed_journey(created, lead["stage"]),
            "delivered_at": _iso(now - timedelta(days=2)) if lead["stage"] >= 9 else None,
            "created_at": _iso(created),
            "updated_at": _iso(updated),
        }
        # A project (Client ID) is opened once the lead is Booked (stage >= 4).
        if lead["stage"] >= 4:
            proj_id = str(uuid.uuid4())
            project_code = f"IJ-2026-{project_counter:04d}"
            project_counter += 1
            proj_doc = {
                "id": proj_id,
                "project_code": project_code,
                "lead_id": lead_id,
                "rough_estimate": lead["tentative_budget"],
                "contract_value": lead["tentative_budget"] if lead["stage"] >= 4 else None,
                "signed_off": lead["stage"] >= 4,
                "sent_to_factory": lead["stage"] >= 9,
                "factory_handover_at": _iso(now - timedelta(days=2)) if lead["stage"] >= 9 else None,
                "created_at": _iso(created),
            }
            await db.projects.insert_one(proj_doc)
            doc["project_id"] = proj_id

            # Site measurement
            ms_id = str(uuid.uuid4())
            ms_doc = {
                "id": ms_id,
                "project_id": proj_id,
                "scheduled_at": _iso(created + timedelta(days=1)),
                "completed_at": _iso(created + timedelta(days=2)) if lead["stage"] >= 6 else None,
                "supervisor_id": supervisor_id,
                "total_area_sqft": 1450 + i * 50 if lead["stage"] >= 6 else None,
                "ceiling_height": 10.5 if lead["stage"] >= 6 else None,
                "status": "Completed" if lead["stage"] >= 6 else "Scheduled",
                "notes": "Standard residential measurement.",
                "created_at": _iso(created + timedelta(hours=4)),
            }
            await db.site_measurements.insert_one(ms_doc)

            # Design revisions (start once the Design stage is reached)
            if lead["stage"] >= 6:
                for rn, st in [(1, "Shared"), (2, "Approved" if lead["stage"] >= 7 else "Revision Requested")]:
                    if rn == 2 and lead["stage"] < 6:
                        continue
                    rev_doc = {
                        "id": str(uuid.uuid4()),
                        "project_id": proj_id,
                        "revision_number": rn,
                        "title": f"R{rn} • {'Initial concept' if rn == 1 else 'Revised layout'}",
                        "designer_id": designer_id,
                        "status": st,
                        "client_feedback": "Looks great, finalize cabinet shutters." if st == "Approved" else "Need taller wall cabinets.",
                        "created_at": _iso(created + timedelta(days=3 + rn)),
                    }
                    await db.design_revisions.insert_one(rev_doc)

            # Payments (milestone rail opens at Booking)
            if lead["stage"] >= 4:
                milestones = [
                    ("Booking Advance", lead["tentative_budget"] * 0.10, "Paid"),
                    ("Design Approval", lead["tentative_budget"] * 0.40, "Paid"),
                    ("Pre-Production", lead["tentative_budget"] * 0.30, "Pending"),
                    ("Handover", lead["tentative_budget"] * 0.20, "Pending"),
                ]
                for j, (mname, amt, st) in enumerate(milestones):
                    await db.payments.insert_one({
                        "id": str(uuid.uuid4()),
                        "project_id": proj_id,
                        "milestone": mname,
                        "amount": round(amt, 2),
                        "due_date": _iso(created + timedelta(days=10 + j * 14)),
                        "paid_date": _iso(created + timedelta(days=11 + j * 14)) if st == "Paid" else None,
                        "status": st,
                        "created_at": _iso(created + timedelta(days=10)),
                    })

        await db.leads.insert_one(doc)
        # Seed initial activity
        await db.activities.insert_one({
            "id": str(uuid.uuid4()),
            "lead_id": lead_id,
            "type": "Note",
            "summary": f"Lead created from {lead['source']}.",
            "actor_id": admin_id,
            "created_at": _iso(created),
        })
        await db.activities.insert_one({
            "id": str(uuid.uuid4()),
            "lead_id": lead_id,
            "type": "Call",
            "summary": "Initial qualification call completed.",
            "actor_id": sales_id,
            "created_at": _iso(created + timedelta(hours=6)),
        })
        if lead["stage"] >= 2:
            await db.stage_history.insert_one({
                "id": str(uuid.uuid4()),
                "lead_id": lead_id,
                "from_stage": 1,
                "to_stage": lead["stage"],
                "changed_by": sales_id,
                "note": "Auto-progressed in seed.",
                "created_at": _iso(created + timedelta(days=1)),
            })
    logger.info("Seeded sample leads")


# <migration name="pipeline_v2">
#   One-time remap of existing leads from the OLD 6-stage pipeline to the NEW
#   9-stage pipeline. Guarded by a settings flag so it runs exactly once and
#   re-deploys are safe. It MUST run before seed_leads so freshly-seeded
#   new-pipeline leads are never remapped. New installs (no leads) just set
#   the flag. Mapping (old -> new), monotonic so no lead moves backward:
#     1 Captured->1 Leads, 2 Consultation->3 Consultation,
#     3 Site Measurement->5, 4 Design->6, 5 Quotation/Sign-off->8 Revised
#     Estimate, 6 Factory->9 Factory Production.
# </migration>
PIPELINE_V2_MAP = {1: 1, 2: 3, 3: 5, 4: 6, 5: 8, 6: 9}


async def migrate_pipeline_stages(db) -> None:
    if await db.settings.find_one({"key": "pipeline_v2_migrated"}):
        return
    moved = 0
    leads = await db.leads.find({}, {"_id": 0}).to_list(100000)
    for l in leads:
        upd = {}
        for field in ("stage", "furthest_stage", "dropped_stage"):
            v = l.get(field)
            if isinstance(v, int) and PIPELINE_V2_MAP.get(v, v) != v:
                upd[field] = PIPELINE_V2_MAP[v]
        if upd:
            await db.leads.update_one({"id": l["id"]}, {"$set": upd})
            moved += 1
    await db.settings.update_one(
        {"key": "pipeline_v2_migrated"},
        {"$set": {"value": {"migrated_at": _iso(datetime.now(timezone.utc)), "leads_moved": moved}}},
        upsert=True,
    )
    logger.info(f"Pipeline v2 migration: remapped {moved} lead(s) to the 9-stage pipeline")


# <maintenance name="purge_ceo_logs">
#   One-time removal of the original CEO account's accumulated audit-log entries
#   (requested clean-up of CEO log records). Targets only the CEO account by
#   email, so the new Tester super-account's logs are untouched. Guarded by a
#   settings flag so it runs exactly once. New CEO activity after this still logs.
# </maintenance>
async def purge_ceo_logs(db) -> None:
    if await db.settings.find_one({"key": "ceo_logs_purged"}):
        return
    ceo_email = os.environ.get("CEO_EMAIL", "ceo@interiojunction.com")
    removed = await db.audit_log.delete_many({"actor_email": ceo_email})
    await db.settings.update_one(
        {"key": "ceo_logs_purged"},
        {"$set": {"value": {"purged_at": _iso(datetime.now(timezone.utc)), "removed": removed, "email": ceo_email}}},
        upsert=True,
    )
    logger.info(f"Purged {removed} audit-log entry(ies) for the CEO account ({ceo_email})")

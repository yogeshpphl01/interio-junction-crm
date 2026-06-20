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
STAGE_SHORT = {1: "Captured", 2: "Consultation", 3: "Site Measurement", 4: "Design", 5: "Quotation", 6: "Factory"}


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
    if stage >= 6:
        return "Completed"
    if stage >= 2:
        return "In-Progress"
    return "Enquiry"


SEED_USERS = [
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
        pwd = admin_pwd if u["role"] == "admin" else default_pwd
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
        "stage": 1,
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
        "stage": 2,
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
        "stage": 3,
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
        "stage": 4,
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
        "stage": 4,
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
        "requirements": "Final quotation pending; signoff in 2 days.",
        "stage": 5,
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
        "stage": 6,
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
            "status": "Active" if lead["stage"] != 6 else "Active",
            "assigned_to": sales_id,
            "created_by": admin_id,
            "project_id": None,
            # <journey-fields>seed the lifecycle bucket + per-stage timeline</journey-fields>
            "lifecycle_phase": _seed_lifecycle(lead["stage"]),
            "furthest_stage": lead["stage"],
            "journey": _seed_journey(created, lead["stage"]),
            "delivered_at": _iso(now - timedelta(days=2)) if lead["stage"] >= 6 else None,
            "created_at": _iso(created),
            "updated_at": _iso(updated),
        }
        # Create project if stage >= 3
        if lead["stage"] >= 3:
            proj_id = str(uuid.uuid4())
            project_code = f"IJ-2026-{project_counter:04d}"
            project_counter += 1
            proj_doc = {
                "id": proj_id,
                "project_code": project_code,
                "lead_id": lead_id,
                "rough_estimate": lead["tentative_budget"],
                "contract_value": lead["tentative_budget"] if lead["stage"] >= 5 else None,
                "signed_off": lead["stage"] >= 5,
                "sent_to_factory": lead["stage"] >= 6,
                "factory_handover_at": _iso(now - timedelta(days=2)) if lead["stage"] >= 6 else None,
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
                "completed_at": _iso(created + timedelta(days=2)) if lead["stage"] >= 4 else None,
                "supervisor_id": supervisor_id,
                "total_area_sqft": 1450 + i * 50 if lead["stage"] >= 4 else None,
                "ceiling_height": 10.5 if lead["stage"] >= 4 else None,
                "status": "Completed" if lead["stage"] >= 4 else "Scheduled",
                "notes": "Standard residential measurement.",
                "created_at": _iso(created + timedelta(hours=4)),
            }
            await db.site_measurements.insert_one(ms_doc)

            # Design revisions
            if lead["stage"] >= 4:
                for rn, st in [(1, "Shared"), (2, "Approved" if lead["stage"] >= 5 else "Revision Requested")]:
                    if rn == 2 and lead["stage"] < 4:
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

            # Payments
            if lead["stage"] >= 5:
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

"""
Seed a DEMO customer so you can walk the customer portal end-to-end without an
SMS gateway. Creates one lead (phone from CLIENT_DEMO_PHONE, default 9998887777)
plus a representative project, a shared estimate, a shared design + render, two
payments, a couple of documents, and a chat thread with a message.

Pair it with the opt-in demo login (NON-PRODUCTION only):

    CLIENT_DEMO_PHONE=9998887777 CLIENT_DEMO_OTP=4821   # set on the backend
    docker compose exec backend python seed_demo_customer.py

Then open the portal, enter 9998887777, tap "Send login code", and type 4821.

Idempotent — safe to re-run (it replaces the demo rows by their fixed ids). It
only ever touches rows whose ids start with "demo-", so it will not disturb real
data. Remove the demo login (unset CLIENT_DEMO_*) before real customer launch.
"""
import os
import asyncio
import logging

from core import db, now_iso

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("seed_demo_customer")


def _norm(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


PHONE = _norm(os.environ.get("CLIENT_DEMO_PHONE", "9998887777")) or "9998887777"

LEAD_ID = "demo-lead-001"
PROJ_ID = "demo-proj-001"
EST_ID = "demo-est-001"
REV_ID = "demo-rev-001"
THREAD_ID = "demo-thread-001"

# collection -> list of rows (each carries its own fixed id, all prefixed "demo-")
ROWS = {
    "leads": [{
        "id": LEAD_ID, "full_name": "Demo Customer", "phone": PHONE,
        "email": "demo.customer@example.com", "city": "Bengaluru", "address": "12 Palm Grove",
        "bhk_type": "2 BHK", "requirements": "Full 2BHK modular — kitchen + 2 wardrobes",
        "source": "Demo", "lead_type": "Residential", "status": "Active", "stage": 5,
        "lifecycle_phase": "design", "project_id": PROJ_ID, "created_at": now_iso(),
    }],
    "projects": [{
        "id": PROJ_ID, "project_code": "IJ-DEMO-01", "contract_value": 850000,
        "booking_paid": True, "activated_at": now_iso(), "sent_to_factory": False,
        "created_at": now_iso(),
    }],
    "estimates": [{
        "id": EST_ID, "lead_id": LEAD_ID, "version": 2, "status": "shared",
        "total": 850000, "currency": "INR", "created_at": now_iso(), "updated_at": now_iso(),
    }],
    "estimate_items": [
        {"id": "demo-item-001", "estimate_id": EST_ID, "description": "Modular kitchen (L-shape)", "quantity": 1, "amount": 420000},
        {"id": "demo-item-002", "estimate_id": EST_ID, "description": "Wardrobe — 8ft sliding", "quantity": 2, "amount": 430000},
    ],
    "design_revisions": [{
        "id": REV_ID, "project_id": PROJ_ID, "revision_number": 3, "status": "Shared",
        "title": "Kitchen + wardrobes — R3", "created_at": now_iso(),
    }],
    "documents": [
        {"id": "demo-doc-001", "project_id": PROJ_ID, "linked_revision_id": REV_ID, "type": "3D Render",
         "original_filename": "kitchen_render.png", "content_type": "image/png", "size": 2400000,
         "storage_path": "demo/kitchen_render.png", "is_deleted": False, "created_at": now_iso()},
        {"id": "demo-doc-002", "project_id": PROJ_ID, "type": "Quotation PDF",
         "original_filename": "quotation_v2.pdf", "content_type": "application/pdf", "size": 180000,
         "storage_path": "demo/quotation_v2.pdf", "is_deleted": False, "created_at": now_iso()},
    ],
    "payments": [
        {"id": "demo-pay-001", "lead_id": LEAD_ID, "project_id": PROJ_ID, "type": "booking",
         "milestone": "Booking (10%)", "amount": 85000, "currency": "INR", "status": "paid",
         "method": "UPI", "paid_date": now_iso(), "created_at": now_iso()},
        {"id": "demo-pay-002", "project_id": PROJ_ID, "type": "milestone",
         "milestone": "Production (40%)", "amount": 340000, "currency": "INR", "status": "due",
         "created_at": now_iso()},
    ],
    "chat_threads": [{
        "id": THREAD_ID, "project_id": PROJ_ID, "lead_id": LEAD_ID, "kind": "group",
        "title": "Your project", "created_by": None, "created_at": now_iso(),
    }],
    "chat_messages": [{
        "id": "demo-msg-001", "thread_id": THREAD_ID, "sender_type": "staff", "sender_id": None,
        "sender_name": "Priya (Project Manager)",
        "body": "Hi! Your R3 renders are ready — take a look and let us know what you think.",
        "created_at": now_iso(),
    }],
}


async def run() -> None:
    await db.connect()
    await db.create_all()   # idempotent; ensures tables exist on a fresh DB
    try:
        # A prior demo customer would hold a customer_id link — clear it so the
        # re-seed is clean and the next login re-creates/links fresh.
        for coll, rows in ROWS.items():
            c = getattr(db, coll)
            for row in rows:
                await c.delete_one({"id": row["id"]})
                await c.insert_one(dict(row))
            log.info("seeded %d row(s) into %s", len(rows), coll)
        # Drop any stale customer record for this phone so login re-creates it
        # against the freshly seeded lead.
        await db.customers.delete_one({"phone": PHONE})
        log.info("DONE. Demo customer ready on phone %s.", PHONE)
        log.info("Log in at the portal with phone %s and the demo code in CLIENT_DEMO_OTP.", PHONE)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run())

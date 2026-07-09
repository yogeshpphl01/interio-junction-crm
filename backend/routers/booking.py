"""
<module name="routers/booking" layer="api">
  <purpose>
    Booking payment + project activation (mobile ecosystem, P0). The 10% booking
    payment is the system pivot: recording a VERIFIED booking payment against a
    lead's accepted estimate ACTIVATES the project — it moves the lead to Booking
    (stage 4), opens the project (Client ID), stamps activation, and records the
    payment. This is the single `on_payment_received()` path used by BOTH the
    manual-UPI verify action (now) and the Razorpay webhook (later) — so nothing
    downstream depends on how the money arrived (see docs/mobile-apps §16 and
    payments/razorpay_booking.reference.py).
  </purpose>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import (
    db, require_permission, ensure_lead_visible, now_iso,
    next_project_code, run_workflow_auto_assign_supervisor, derive_lifecycle_phase,
)
from audit import log_audit

router = APIRouter()

BOOKING_PERCENT = 0.10


class BookingPaymentIn(BaseModel):
    method: str = "manual_upi"          # manual_upi | razorpay
    reference: Optional[str] = None     # UPI transaction ref / gateway payment id
    screenshot_ref: Optional[str] = None
    amount: Optional[float] = None      # override; default = 10% of the accepted estimate


@router.post("/leads/{lead_id}/booking-payment")
async def record_booking_payment(lead_id: str, payload: BookingPaymentIn, request: Request,
                                  user: dict = Depends(require_permission("payments.manage"))):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)

    # Idempotency: one booking payment per lead.
    if await db.payments.find_one({"lead_id": lead_id, "type": "booking"}):
        raise HTTPException(status_code=409, detail="A booking payment is already recorded for this lead")

    # The amount is derived from the ACCEPTED estimate (never trusted from the client).
    est_rows = await db.estimates.find({"lead_id": lead_id, "status": "accepted"}, {"_id": 0}).sort("version", -1).to_list(1)
    if not est_rows:
        raise HTTPException(status_code=400, detail="No accepted estimate — the customer must accept an estimate before booking")
    est = est_rows[0]
    amount = round(payload.amount if payload.amount is not None else est["total"] * BOOKING_PERCENT, 2)
    ts = now_iso()

    # 1) Record the verified booking payment.
    payment = {
        "id": str(uuid.uuid4()), "project_id": lead.get("project_id"), "lead_id": lead_id,
        "type": "booking", "milestone": "Booking Advance (10%)", "amount": amount,
        "currency": est.get("currency", "INR"), "method": payload.method, "reference": payload.reference,
        "screenshot_ref": payload.screenshot_ref, "status": "verified",
        "verified_by": user["id"], "verified_at": ts, "paid_date": ts, "due_date": None, "created_at": ts,
    }
    await db.payments.insert_one(payment)

    # 2) on_payment_received: activate the project (move to Booking + open the Client ID).
    from_stage = int(lead.get("stage") or 1)
    lead_update: dict = {"updated_at": ts}
    if from_stage < 4:
        lead_update["stage"] = 4
        lead_update["furthest_stage"] = max(int(lead.get("furthest_stage") or from_stage), 4)
        lead_update["lifecycle_phase"] = derive_lifecycle_phase(4, lead.get("status", "Active"))

    project_id = lead.get("project_id")
    project_code = None
    if not project_id:
        project_code = await next_project_code()
        proj = {
            "id": str(uuid.uuid4()), "project_code": project_code, "lead_id": lead_id,
            "rough_estimate": lead.get("tentative_budget", 0), "contract_value": est["total"],
            "signed_off": True, "booking_paid": True, "activated_at": ts,
            "sent_to_factory": False, "factory_handover_at": None, "created_at": ts,
        }
        await db.projects.insert_one(proj)
        project_id = proj["id"]
        lead_update["project_id"] = project_id
        await log_audit(db, user, "project.created", "project", project_id, project_code, {"lead_id": lead_id})
        await run_workflow_auto_assign_supervisor(lead_id, project_id)
    else:
        await db.projects.update_one({"id": project_id}, {"$set": {
            "signed_off": True, "booking_paid": True, "activated_at": ts, "contract_value": est["total"],
        }})
        pr = await db.projects.find_one({"id": project_id}, {"_id": 0})
        project_code = pr.get("project_code") if pr else None

    # Link the payment to the (now-existing) project (DB row + the dict we return).
    if not payment["project_id"]:
        payment["project_id"] = project_id
        await db.payments.update_one({"id": payment["id"]}, {"$set": {"project_id": project_id}})
    await db.leads.update_one({"id": lead_id}, {"$set": lead_update})

    if from_stage < 4:
        await db.stage_history.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lead_id, "from_stage": from_stage, "to_stage": 4,
            "changed_by": user["id"], "note": "Booking payment received — project activated", "created_at": ts,
        })
    await db.activities.insert_one({
        "id": str(uuid.uuid4()), "lead_id": lead_id, "type": "Note",
        "summary": f"Booking payment ({payload.method}) verified — project {project_code} activated.",
        "actor_id": user["id"], "created_at": ts,
    })
    await log_audit(db, user, "payment.received", "project", project_id, project_code,
                    {"lead_id": lead_id, "amount": amount, "method": payload.method, "channel": payload.method}, request)

    payment.pop("_id", None)
    return {
        "activated": True,
        "lead_id": lead_id,
        "stage": 4,
        "project_id": project_id,
        "project_code": project_code,
        "payment": payment,
        # Chat/groups arrive with the app track; this flags the DM->group conversion to do.
        "group_creation_pending": True,
    }

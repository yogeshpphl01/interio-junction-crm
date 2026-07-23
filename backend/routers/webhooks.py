"""
<module name="routers/webhooks" layer="api">
  <purpose>
    Payment-gateway webhooks (Razorpay) — the AUTHORITATIVE confirmation path
    for gateway payments (P1-13, N2). Every callback is verified by its
    HMAC-SHA256 signature (dependency-free), deduplicated for idempotency (a
    replay never activates a project twice), and amount/currency-matched against
    the recorded order before it can mark a payment verified. A verified capture
    fires the SAME activation as the manual-UPI path (booking.py) — downstream
    does not care how the money arrived.
  </purpose>
  <safety>
    Inert until RAZORPAY_WEBHOOK_SECRET is configured (503), so no unauthenticated
    endpoint accepts events by default. Secrets live in the env / Secret Manager.
  </safety>
</module>
"""
import os
import json
import hmac
import uuid
import hashlib
import logging
from fastapi import APIRouter, Request, HTTPException

from core import db, now_iso, derive_lifecycle_phase
from audit import log_audit
from push import send_push

logger = logging.getLogger(__name__)
router = APIRouter()


def _webhook_secret() -> str:
    return os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")


def _verify_signature(raw: bytes, signature: str) -> bool:
    """Constant-time HMAC-SHA256 verification of the Razorpay webhook signature."""
    secret = _webhook_secret()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _finalize_activation(payment: dict, channel: str, request: Request) -> None:
    """Shared 'on payment received' tail: mark the project booked/activated, move
    the lead to Booking, timeline + audit, notify the customer. Mirrors the manual
    verify path (booking.py) so both channels converge on `payment.received`."""
    project_id = payment.get("project_id")
    lead = None
    if payment.get("lead_id"):
        lead = await db.leads.find_one({"id": payment["lead_id"]}, {"_id": 0})
    elif project_id:
        lead = await db.leads.find_one({"project_id": project_id}, {"_id": 0})
    ts = now_iso()
    project_code = None
    if project_id:
        await db.projects.update_one({"id": project_id}, {"$set": {
            "signed_off": True, "booking_paid": True, "activated_at": ts,
        }})
        pr = await db.projects.find_one({"id": project_id}, {"_id": 0, "project_code": 1})
        project_code = (pr or {}).get("project_code")
    if lead:
        from_stage = int(lead.get("stage") or 1)
        lead_update = {"updated_at": ts}
        if from_stage < 4:
            lead_update["stage"] = 4
            lead_update["furthest_stage"] = max(int(lead.get("furthest_stage") or from_stage), 4)
            lead_update["lifecycle_phase"] = derive_lifecycle_phase(4, lead.get("status", "Active"))
            await db.stage_history.insert_one({
                "id": str(uuid.uuid4()), "lead_id": lead["id"], "from_stage": from_stage, "to_stage": 4,
                "changed_by": None, "note": "Booking payment received (gateway) — project activated",
                "created_at": ts,
            })
        await db.leads.update_one({"id": lead["id"]}, {"$set": lead_update})
        if lead.get("customer_id"):
            await send_push("customer", lead["customer_id"], "Booking confirmed 🎉",
                            f"We've received your booking payment — project {project_code} is now active.",
                            data={"type": "booking", "project_id": project_id}, lead_id=lead["id"])
    await log_audit(db, None, "payment.received", "project", project_id, project_code,
                    {"amount": payment.get("amount"), "channel": channel,
                     "gateway_payment_id": payment.get("gateway_payment_id")}, request)


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    if not _webhook_secret():
        raise HTTPException(status_code=503, detail="Payment gateway is not configured")
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not _verify_signature(raw, signature):
        await log_audit(db, None, "payment.webhook_rejected", "payment", None, None,
                        {"reason": "bad_signature"}, request)
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed payload")

    event_id = request.headers.get("X-Razorpay-Event-Id") or event.get("id") or str(uuid.uuid4())
    # Idempotency: a repeat of the same gateway event id is a no-op.
    if await db.gateway_events.find_one({"id": event_id}, {"_id": 0, "id": 1}):
        return {"ok": True, "idempotent": True}

    kind = event.get("event")
    if kind == "payment.captured":
        result = await _handle_capture(event, request)
    elif kind in ("refund.processed", "refund.created"):
        result = await _handle_refund(event, request)
    else:
        result = {"ok": True, "ignored": kind}

    await db.gateway_events.insert_one({
        "id": event_id, "event_type": kind, "payment_id": result.get("payment_id"),
        "processed_at": now_iso(),
    })
    return {k: v for k, v in result.items() if k != "payment_id"} or {"ok": True}


async def _handle_capture(event: dict, request: Request) -> dict:
    try:
        pay = event["payload"]["payment"]["entity"]
    except (KeyError, TypeError):
        return {"ok": True, "ignored": "no_payment_entity"}
    order_id = pay.get("order_id")
    rec = await db.payments.find_one({"gateway_order_id": order_id}, {"_id": 0}) if order_id else None
    if not rec:
        return {"ok": True, "ignored": "unknown_order"}
    if rec.get("status") == "verified":
        return {"ok": True, "idempotent": True, "payment_id": rec["id"]}
    # Anti-tamper: the captured amount (paise) must equal our recorded amount.
    if int(round((rec.get("amount") or 0) * 100)) != int(pay.get("amount") or -1):
        await log_audit(db, None, "payment.amount_mismatch", "payment", rec["id"], rec.get("milestone"),
                        {"expected_paise": int(round((rec.get('amount') or 0) * 100)), "got_paise": pay.get("amount")}, request)
        raise HTTPException(status_code=400, detail="Amount mismatch")
    await db.payments.update_one({"id": rec["id"]}, {"$set": {
        "status": "verified", "gateway": "razorpay", "gateway_payment_id": pay.get("id"),
        "verified_at": now_iso(), "paid_date": now_iso(),
    }})
    rec.update(status="verified", gateway_payment_id=pay.get("id"))
    await log_audit(db, None, "payment.webhook_verified", "payment", rec["id"], rec.get("milestone"),
                    {"gateway_payment_id": pay.get("id"), "amount": rec.get("amount")}, request)
    await _finalize_activation(rec, "razorpay", request)
    return {"ok": True, "verified": True, "payment_id": rec["id"]}


async def _handle_refund(event: dict, request: Request) -> dict:
    try:
        refund = event["payload"]["refund"]["entity"]
    except (KeyError, TypeError):
        return {"ok": True, "ignored": "no_refund_entity"}
    pay_id = refund.get("payment_id")
    rec = await db.payments.find_one({"gateway_payment_id": pay_id}, {"_id": 0}) if pay_id else None
    if not rec:
        return {"ok": True, "ignored": "unknown_payment"}
    await db.payments.update_one({"id": rec["id"]}, {"$set": {
        "status": "refunded", "refunded_at": now_iso(),
        "refund_amount": (refund.get("amount") or 0) / 100,
    }})
    await log_audit(db, None, "payment.refunded", "payment", rec["id"], rec.get("milestone"),
                    {"gateway": "razorpay", "amount": (refund.get("amount") or 0) / 100, "channel": "gateway"}, request)
    return {"ok": True, "refunded": True, "payment_id": rec["id"]}

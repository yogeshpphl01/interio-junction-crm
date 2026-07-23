"""
<module name="routers/payments" layer="api">
  <purpose>Milestone payment rail per project. Recording a milestone and
  CONFIRMING it (marking Paid) are separated duties (SoD, NIST AC-5):
  `payments.record` creates/edits; `payments.confirm` marks Paid — and the
  confirmer may not be the person who recorded it (four-eyes). The 50%-paid rule
  in evaluate_gate uses these rows to gate the move to Factory.</purpose>
  <endpoints>
    POST  /api/payments        -> create a milestone (payments.record).
    PATCH /api/payments/{pid}   -> update; marking Paid needs payments.confirm + four-eyes.
  </endpoints>
</module>
"""
import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from core import (
    db, require_any_permission, require_permission, has_any, deny_self_action, assert_step_up,
    PaymentInput, PaymentUpdate, now_iso,
)
from audit import log_audit

router = APIRouter()


def _dual_control_threshold() -> float:
    """Payments at/above this amount force a fresh step-up on confirm/refund even
    when STEP_UP_ENABLED is off (0/unset = no forced step-up). Set once MFA is
    rolled out (see PAYMENT_STEP_UP_THRESHOLD)."""
    try:
        return float(os.environ.get("PAYMENT_STEP_UP_THRESHOLD", "0") or 0)
    except ValueError:
        return 0.0


class RefundIn(BaseModel):
    amount: Optional[float] = None
    reason: Optional[str] = None


@router.post("/payments")
async def create_payment(payload: PaymentInput,
                         user: dict = Depends(require_any_permission("payments.record", "payments.manage"))):
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "paid_date": None,
        "status": "Pending",
        "created_by": user["id"],     # recorded-by, for the four-eyes confirm check
        "confirmed_by": None,
        "created_at": now_iso(),
    }
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, user, "payment.created", "payment", doc["id"], payload.milestone,
                    {"amount": payload.amount, "project_id": payload.project_id})
    return doc


@router.patch("/payments/{pid}")
async def update_payment(pid: str, payload: PaymentUpdate, request: Request,
                         user: dict = Depends(require_any_permission("payments.record", "payments.confirm", "payments.manage"))):
    existing = await db.payments.find_one({"id": pid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Payment not found")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    confirming = update.get("status") == "Paid" and existing.get("status") != "Paid"
    if confirming:
        # Marking money as received is a CONFIRM action: needs the finance
        # permission, a fresh step-up, and a different person than who recorded it.
        if not has_any(user, "payments.confirm", "payments.manage"):
            raise HTTPException(status_code=403, detail="Forbidden: confirming a payment requires 'payments.confirm'")
        # Large payments force a step-up regardless of the global flag (dual control).
        threshold = _dual_control_threshold()
        big = bool(threshold) and float(existing.get("amount") or 0) >= threshold
        await assert_step_up(request, user, force=big)
        deny_self_action(existing.get("created_by"), user, "payment")
        if not update.get("paid_date"):
            update["paid_date"] = now_iso()
        update["confirmed_by"] = user["id"]
    await db.payments.update_one({"id": pid}, {"$set": update})
    new_p = await db.payments.find_one({"id": pid}, {"_id": 0})
    if confirming:
        await log_audit(db, user, "payment.paid", "payment", pid, new_p.get("milestone"), {"amount": new_p.get("amount")})
    else:
        await log_audit(db, user, "payment.updated", "payment", pid, new_p.get("milestone"), {"fields": list(update.keys())})
    return new_p


@router.post("/payments/{pid}/refund")
async def refund_payment(pid: str, body: RefundIn, request: Request,
                         user: dict = Depends(require_permission("payments.refund"))):
    """Issue a refund — the most sensitive money move, so it is under dual control:
    a dedicated `payments.refund` permission (finance/CEO only, never Sales/Admin),
    four-eyes (the refunder may not be the person who confirmed the payment), and a
    forced step-up. Fully audited."""
    rec = await db.payments.find_one({"id": pid}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Payment not found")
    if rec.get("status") not in ("Paid", "verified"):
        raise HTTPException(status_code=409, detail="Only a paid/verified payment can be refunded")
    if rec.get("status") == "refunded" or rec.get("refunded_at"):
        raise HTTPException(status_code=409, detail="Payment is already refunded")
    # Four-eyes: whoever confirmed the money cannot also refund it.
    deny_self_action(rec.get("confirmed_by") or rec.get("verified_by"), user, "payment refund")
    # Step-up: forced for a large refund (>= threshold); otherwise respects the
    # global STEP_UP_ENABLED — so refunds aren't hard-blocked before MFA rollout.
    threshold = _dual_control_threshold()
    big = bool(threshold) and float(rec.get("amount") or 0) >= threshold
    await assert_step_up(request, user, force=big)
    amount = rec.get("amount") if body.amount is None else round(float(body.amount), 2)
    if amount is None or amount <= 0 or amount > float(rec.get("amount") or 0):
        raise HTTPException(status_code=400, detail="Invalid refund amount")
    await db.payments.update_one({"id": pid}, {"$set": {
        "status": "refunded", "refunded_at": now_iso(), "refund_amount": amount, "refunded_by": user["id"],
    }})
    await log_audit(db, user, "payment.refunded", "payment", pid, rec.get("milestone"),
                    {"amount": amount, "reason": (body.reason or "")[:300], "channel": "manual"}, request)
    return {"ok": True, "refunded": True, "amount": amount, "payment_id": pid}

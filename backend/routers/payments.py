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
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from core import (
    db, require_any_permission, has_any, deny_self_action, assert_step_up,
    PaymentInput, PaymentUpdate, now_iso,
)
from audit import log_audit

router = APIRouter()


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
        await assert_step_up(request, user)
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

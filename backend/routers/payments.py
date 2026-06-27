"""
<module name="routers/payments" layer="api">
  <purpose>Milestone payment rail per project (admin/sales). The 50%-paid rule
  in evaluate_gate uses these rows to gate the move to Factory.</purpose>
  <endpoints>
    POST  /api/payments        -> create a milestone.
    PATCH /api/payments/{pid}   -> update; marking Paid stamps paid_date.
  </endpoints>
</module>
"""
import uuid
from fastapi import APIRouter, Depends
from core import db, require_permission, PaymentInput, PaymentUpdate, now_iso
from audit import log_audit

router = APIRouter()


@router.post("/payments")
async def create_payment(payload: PaymentInput, user: dict = Depends(require_permission("payments.manage"))):
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "paid_date": None,
        "created_at": now_iso(),
    }
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, user, "payment.created", "payment", doc["id"], payload.milestone,
                    {"amount": payload.amount, "project_id": payload.project_id})
    return doc


@router.patch("/payments/{pid}")
async def update_payment(pid: str, payload: PaymentUpdate, user: dict = Depends(require_permission("payments.manage"))):
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if update.get("status") == "Paid" and not update.get("paid_date"):
        update["paid_date"] = now_iso()
    await db.payments.update_one({"id": pid}, {"$set": update})
    new_p = await db.payments.find_one({"id": pid}, {"_id": 0})
    if update.get("status") == "Paid":
        await log_audit(db, user, "payment.paid", "payment", pid, new_p.get("milestone"), {"amount": new_p.get("amount")})
    else:
        await log_audit(db, user, "payment.updated", "payment", pid, new_p.get("milestone"), {"fields": list(update.keys())})
    return new_p

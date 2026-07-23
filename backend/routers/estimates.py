"""
<module name="routers/estimates" layer="api">
  <purpose>
    Estimate engine (mobile ecosystem, P0). Versioned estimates with a built-in
    approval workflow:
        draft -> submitted -> approved -> shared -> accepted
        submitted -> changes_requested -> (revise) -> draft
    Creating / editing / sharing needs 'estimates.create' (Sales Executive);
    approving / rejecting needs 'estimates.approve' (Project Manager / Marketing
    Head). Totals are ALWAYS computed server-side from the line items (never
    trusted from the client) — this is what the booking payment is derived from.
  </purpose>
  <later>
    PDF generation, the pluggable pricing engine (owner's Excel), and customer
    acceptance via the Client App plug in here without changing this workflow.
  </later>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import (
    db, get_current_user, has_permission, require_permission,
    deny_self_action, assert_step_up,
    ensure_lead_visible, visible_lead_ids, now_iso,
)
from audit import log_audit
from push import send_push

router = APIRouter()

# Workflow states.
DRAFT, SUBMITTED, APPROVED, SHARED, ACCEPTED, CHANGES = (
    "draft", "submitted", "approved", "shared", "accepted", "changes_requested",
)


class EstimateItemIn(BaseModel):
    category: Optional[str] = None
    description: str
    unit: Optional[str] = None
    quantity: float = 1
    rate: float = 0
    meta: Optional[dict] = None


class EstimateIn(BaseModel):
    lead_id: str
    currency: str = "INR"
    discount: float = 0          # absolute amount off the subtotal
    tax_percent: float = 0       # e.g. 18 for 18% GST, applied after discount
    valid_until: Optional[str] = None
    items: list[EstimateItemIn] = []


def _totals(items: list[EstimateItemIn], discount: float, tax_percent: float) -> dict:
    subtotal = round(sum((i.quantity or 0) * (i.rate or 0) for i in items), 2)
    after_discount = max(subtotal - (discount or 0), 0)
    tax_amount = round(after_discount * (tax_percent or 0) / 100.0, 2)
    total = round(after_discount + tax_amount, 2)
    return {"subtotal": subtotal, "discount": round(discount or 0, 2), "tax": tax_amount, "total": total}


async def _lead_or_404_visible(user: dict, lead_id: str) -> dict:
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    return lead


async def _with_items(est: dict) -> dict:
    est["items"] = await db.estimate_items.find({"estimate_id": est["id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return est


@router.get("/estimates")
async def list_estimates(
    user: dict = Depends(get_current_user),
    lead_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """List estimates, scoped to leads the user can see (own for SE, all for
    PM/MH). `status=submitted` gives the approval queue."""
    filt: dict = {}
    ids = await visible_lead_ids(user)  # None => full visibility
    if lead_id:
        await _lead_or_404_visible(user, lead_id)
        filt["lead_id"] = lead_id
    elif ids is not None:
        filt["lead_id"] = {"$in": list(ids)}
    if project_id:
        filt["project_id"] = project_id
    if status:
        filt["status"] = status
    rows = await db.estimates.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.get("/estimates/{estimate_id}")
async def get_estimate(estimate_id: str, user: dict = Depends(get_current_user)):
    est = await db.estimates.find_one({"id": estimate_id}, {"_id": 0})
    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")
    await _lead_or_404_visible(user, est["lead_id"])
    return await _with_items(est)


@router.post("/estimates")
async def create_estimate(payload: EstimateIn, user: dict = Depends(require_permission("estimates.create"))):
    lead = await _lead_or_404_visible(user, payload.lead_id)
    if not payload.items:
        raise HTTPException(status_code=400, detail="An estimate needs at least one line item")
    # Version = next after the newest existing estimate for this lead.
    prev = await db.estimates.find({"lead_id": payload.lead_id}, {"_id": 0}).sort("version", -1).to_list(1)
    version = (prev[0]["version"] + 1) if prev else 1
    t = _totals(payload.items, payload.discount, payload.tax_percent)
    ts = now_iso()
    est = {
        "id": str(uuid.uuid4()),
        "lead_id": payload.lead_id,
        "project_id": lead.get("project_id"),
        "version": version,
        "status": DRAFT,
        "currency": payload.currency,
        "valid_until": payload.valid_until,
        "pdf_ref": None,
        "created_by": user["id"],
        "approved_by": None,
        "created_at": ts,
        "updated_at": ts,
        **t,
    }
    await db.estimates.insert_one(est)
    for it in payload.items:
        await db.estimate_items.insert_one({
            "id": str(uuid.uuid4()),
            "estimate_id": est["id"],
            "category": it.category,
            "description": it.description,
            "unit": it.unit,
            "quantity": it.quantity,
            "rate": it.rate,
            "amount": round((it.quantity or 0) * (it.rate or 0), 2),
            "meta": it.meta or {},
            "created_at": ts,
        })
    est.pop("_id", None)
    await log_audit(db, user, "estimate.created", "estimate", est["id"], f"v{version} · {lead.get('full_name')}",
                    {"lead_id": payload.lead_id, "total": t["total"]})
    return await _with_items(est)


async def _transition(estimate_id: str, user: dict, *, allow_from: set, to: str, action: str, extra: Optional[dict] = None) -> dict:
    est = await db.estimates.find_one({"id": estimate_id}, {"_id": 0})
    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")
    await _lead_or_404_visible(user, est["lead_id"])
    if est["status"] not in allow_from:
        raise HTTPException(status_code=409, detail=f"Cannot {action} an estimate in '{est['status']}' state")
    update = {"status": to, "updated_at": now_iso(), **(extra or {})}
    await db.estimates.update_one({"id": estimate_id}, {"$set": update})
    await log_audit(db, user, f"estimate.{action}", "estimate", estimate_id, f"v{est['version']}",
                    {"from": est["status"], "to": to})
    return await _with_items(await db.estimates.find_one({"id": estimate_id}, {"_id": 0}))


@router.post("/estimates/{estimate_id}/submit")
async def submit_estimate(estimate_id: str, user: dict = Depends(require_permission("estimates.create"))):
    """SE submits a draft for Project-Manager approval."""
    return await _transition(estimate_id, user, allow_from={DRAFT, CHANGES}, to=SUBMITTED, action="submitted")


@router.post("/estimates/{estimate_id}/approve")
async def approve_estimate(estimate_id: str, request: Request, user: dict = Depends(require_permission("estimates.approve"))):
    """PM / Marketing Head approves a submitted estimate. Four-eyes: the approver
    may not be the estimate's creator (SoD), and a step-up may be required."""
    est = await db.estimates.find_one({"id": estimate_id}, {"_id": 0, "created_by": 1})
    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")
    deny_self_action(est.get("created_by"), user, "estimate")
    await assert_step_up(request, user)
    return await _transition(estimate_id, user, allow_from={SUBMITTED}, to=APPROVED, action="approved",
                             extra={"approved_by": user["id"]})


@router.post("/estimates/{estimate_id}/reject")
async def reject_estimate(estimate_id: str, user: dict = Depends(require_permission("estimates.approve"))):
    """PM / Marketing Head sends a submitted estimate back for changes."""
    return await _transition(estimate_id, user, allow_from={SUBMITTED}, to=CHANGES, action="rejected")


@router.post("/estimates/{estimate_id}/share")
async def share_estimate(estimate_id: str, user: dict = Depends(require_permission("estimates.create"))):
    """SE shares an approved estimate with the customer. (PDF generation later.)"""
    est = await _transition(estimate_id, user, allow_from={APPROVED}, to=SHARED, action="shared")
    # Nudge the customer on the Client App (no-op until they've linked a device).
    lead = await db.leads.find_one({"id": est["lead_id"]}, {"_id": 0, "customer_id": 1})
    if lead and lead.get("customer_id"):
        await send_push("customer", lead["customer_id"], "New estimate to review",
                        "Your estimate is ready — tap to review and accept.",
                        data={"type": "estimate", "estimate_id": estimate_id}, lead_id=est["lead_id"])
    return est


@router.post("/estimates/{estimate_id}/accept")
async def accept_estimate(estimate_id: str, user: dict = Depends(require_permission("estimates.create"))):
    """Customer acceptance. For now the SE records it on the customer's behalf;
    the Client App will call this directly once customer auth ships. Acceptance
    is what unlocks the 10% booking payment (§16)."""
    return await _transition(estimate_id, user, allow_from={SHARED}, to=ACCEPTED, action="accepted")

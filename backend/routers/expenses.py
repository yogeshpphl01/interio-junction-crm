"""
<module name="routers/expenses" layer="api">
  <purpose>
    Site expenses (mobile ecosystem, P0). The Site Manager captures a bill (photo)
    and submits it ('expenses.submit'); the Project Manager / Marketing Head
    approves or rejects it ('expenses.approve') — a separation-of-duties workflow
    (whoever spends is not who approves). Reads are open to either party or anyone
    who can see the project.
  </purpose>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import (
    db, get_current_user, has_permission, require_permission,
    deny_self_action, assert_step_up, ensure_project_visible, now_iso,
)
from audit import log_audit

router = APIRouter()


class ExpenseIn(BaseModel):
    project_id: str
    amount: float
    currency: str = "INR"
    note: Optional[str] = None
    bill_photo_ref: Optional[str] = None


class DecisionIn(BaseModel):
    note: Optional[str] = None


async def _read_guard(user: dict, project_id: str) -> None:
    if has_permission(user, "expenses.submit") or has_permission(user, "expenses.approve"):
        return
    await ensure_project_visible(user, project_id)


@router.post("/expenses")
async def submit_expense(payload: ExpenseIn, user: dict = Depends(require_permission("expenses.submit"))):
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    if not await db.projects.find_one({"id": payload.project_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Project not found")
    doc = {
        "id": str(uuid.uuid4()), "project_id": payload.project_id,
        "amount": round(payload.amount, 2), "currency": payload.currency, "note": payload.note,
        "bill_photo_ref": payload.bill_photo_ref, "status": "submitted",
        "submitted_by": user["id"], "approved_by": None,
        "created_at": now_iso(), "decided_at": None,
    }
    await db.expenses.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, user, "expense.submitted", "expense", doc["id"], f"{payload.currency} {doc['amount']}",
                    {"project_id": payload.project_id})
    return doc


@router.get("/expenses")
async def list_expenses(user: dict = Depends(get_current_user), project_id: str = None, status: Optional[str] = None):
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    await _read_guard(user, project_id)
    filt: dict = {"project_id": project_id}
    if status:
        filt["status"] = status
    return await db.expenses.find(filt, {"_id": 0}).sort("created_at", -1).to_list(2000)


async def _decide(expense_id: str, user: dict, request: Request, to_status: str, action: str) -> dict:
    exp = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    if exp["status"] != "submitted":
        raise HTTPException(status_code=409, detail=f"Expense is already '{exp['status']}'")
    # Four-eyes: whoever submitted the bill cannot approve/reject it (SoD).
    deny_self_action(exp.get("submitted_by"), user, "expense")
    await assert_step_up(request, user)
    await db.expenses.update_one({"id": expense_id}, {"$set": {
        "status": to_status, "approved_by": user["id"], "decided_at": now_iso(),
    }})
    await log_audit(db, user, f"expense.{action}", "expense", expense_id, f"{exp['currency']} {exp['amount']}",
                    {"project_id": exp["project_id"]})
    return await db.expenses.find_one({"id": expense_id}, {"_id": 0})


@router.post("/expenses/{expense_id}/approve")
async def approve_expense(expense_id: str, request: Request, payload: DecisionIn = DecisionIn(), user: dict = Depends(require_permission("expenses.approve"))):
    return await _decide(expense_id, user, request, "approved", "approved")


@router.post("/expenses/{expense_id}/reject")
async def reject_expense(expense_id: str, request: Request, payload: DecisionIn = DecisionIn(), user: dict = Depends(require_permission("expenses.approve"))):
    return await _decide(expense_id, user, request, "rejected", "rejected")

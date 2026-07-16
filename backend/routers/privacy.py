"""
<module name="routers/privacy" layer="api">
  <purpose>
    Staff-side DPDP handling (P1-11): review erasure requests and erase (anonymize)
    a customer on request. Erasure de-identifies the personal data (name, phone,
    email) across the customer record and their linked leads, revokes the
    customer's sessions, and closes the request — while RETAINING the transactional
    rows (leads/estimates/payments) that the business must keep for tax/legal
    retention (DPDP Act 2023 §8(7)). A destructive, privileged action, so it
    requires account-management rights + a fresh step-up and is fully audited.
  </purpose>
</module>
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from core import db, require_permission, revoke_tokens, assert_step_up, now_iso
from audit import log_audit

router = APIRouter()


@router.get("/erasure-requests")
async def list_erasure_requests(status: str = "pending",
                                admin: dict = Depends(require_permission("users.manage"))):
    """List DPDP erasure requests (default: pending) for staff to action."""
    filt = {} if status == "all" else {"status": status}
    rows = await db.erasure_requests.find(filt, {"_id": 0}).sort("requested_at", -1).to_list(2000)
    # enrich with the (possibly still-identified) customer name for the queue UI
    for r in rows:
        c = await db.customers.find_one({"id": r.get("customer_id")}, {"_id": 0, "full_name": 1, "erased_at": 1})
        r["customer_name"] = (c or {}).get("full_name")
        r["already_erased"] = bool((c or {}).get("erased_at"))
    return rows


async def _anonymize_customer(customer_id: str) -> bool:
    """De-identify a customer + their linked leads. Returns False if not found."""
    cust = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not cust:
        return False
    ts = now_iso()
    # Unique redacted values so the phone/email UNIQUE constraints don't collide.
    redacted = f"erased:{customer_id}"
    await db.customers.update_one({"id": customer_id}, {"$set": {
        "full_name": "[erased]",
        "phone": redacted,
        "email": f"{redacted}@erased.invalid",
        "auth_uid": None,
        "is_active": False,
        "erased_at": ts,
    }})
    await revoke_tokens(db.customers, customer_id)  # kill any live customer session
    # Strip PII from the customer's leads but keep the transactional rows.
    leads = await db.leads.find({"customer_id": customer_id}, {"_id": 0, "id": 1}).to_list(1000)
    for l in leads:
        await db.leads.update_one({"id": l["id"]}, {"$set": {
            "full_name": "[erased]", "phone": redacted, "email": None,
        }})
    return True


@router.post("/customers/{customer_id}/erase")
async def erase_customer(customer_id: str, request: Request,
                         admin: dict = Depends(require_permission("users.manage"))):
    """Fulfil a DPDP erasure: anonymize the customer + leads, revoke sessions,
    close any pending request. Requires a fresh step-up."""
    await assert_step_up(request, admin)
    cust = await db.customers.find_one({"id": customer_id}, {"_id": 0, "full_name": 1, "erased_at": 1})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if cust.get("erased_at"):
        raise HTTPException(status_code=409, detail="Customer is already erased")
    ok = await _anonymize_customer(customer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.erasure_requests.update_one(
        {"customer_id": customer_id, "status": "pending"},
        {"$set": {"status": "completed", "decided_by": admin["id"], "decided_at": now_iso()}},
    )
    await log_audit(db, admin, "privacy.erased", "customer", customer_id, cust.get("full_name"),
                    {"retained": "transactional records kept per DPDP §8(7)"}, request)
    return {"ok": True, "erased": True, "customer_id": customer_id}


@router.post("/erasure-requests/{request_id}/reject")
async def reject_erasure(request_id: str, request: Request,
                         admin: dict = Depends(require_permission("users.manage"))):
    """Reject an erasure request (e.g. an active project with outstanding dues);
    the reason is recorded for accountability."""
    rec = await db.erasure_requests.find_one({"id": request_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Request not found")
    if rec.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Request is already '{rec.get('status')}'")
    await db.erasure_requests.update_one({"id": request_id}, {"$set": {
        "status": "rejected", "decided_by": admin["id"], "decided_at": now_iso(),
    }})
    await log_audit(db, admin, "privacy.erasure_rejected", "customer", rec.get("customer_id"), None,
                    {"request_id": request_id}, request)
    return {"ok": True, "status": "rejected"}

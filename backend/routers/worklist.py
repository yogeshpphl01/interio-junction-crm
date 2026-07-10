"""
<module name="routers/worklist" layer="api">
  <purpose>
    The Company App's mobile home feed — the employee counterpart to the Client
    App's /client/projects. GET /me/worklist returns a role-appropriate set of
    "things you need to act on" buckets, assembled purely from what the signed-in
    user is PERMITTED to do (has_permission, not hardcoded roles) so custom
    account categories get the right home screen automatically:

      estimates.approve -> estimates awaiting your approval
      expenses.approve  -> expenses awaiting your approval
      tickets.manage    -> open tickets assigned to you
      (personal pipeline) -> your active leads not yet booked

    Every bucket carries a count (for a badge) and the underlying items (for the
    list), so one call paints the whole home screen.
  </purpose>
</module>
"""
from fastapi import APIRouter, Depends

from core import db, get_current_user, has_permission, visible_lead_ids

router = APIRouter()


async def _lead_names(lead_ids: list[str]) -> dict:
    uniq = list({lid for lid in lead_ids if lid})
    if not uniq:
        return {}
    docs = await db.leads.find({"id": {"$in": uniq}}, {"_id": 0, "id": 1, "full_name": 1}).to_list(500)
    return {d["id"]: d.get("full_name") for d in docs}


@router.get("/me/worklist")
async def my_worklist(user: dict = Depends(get_current_user)):
    buckets = []

    # --- Approvals: estimates ---
    if has_permission(user, "estimates.approve"):
        rows = await db.estimates.find({"status": "submitted"}, {"_id": 0}).sort("created_at", 1).to_list(50)
        names = await _lead_names([e["lead_id"] for e in rows])
        items = [{
            "id": e["id"], "version": e.get("version"), "lead_id": e.get("lead_id"),
            "lead_name": names.get(e.get("lead_id")), "total": e.get("total"),
            "currency": e.get("currency"), "created_at": e.get("created_at"),
        } for e in rows]
        buckets.append({"key": "estimate_approvals", "label": "Estimates to approve",
                        "action": "estimates.approve", "count": len(items), "items": items})

    # --- Approvals: expenses ---
    if has_permission(user, "expenses.approve"):
        rows = await db.expenses.find({"status": "submitted"}, {"_id": 0}).sort("created_at", 1).to_list(50)
        buckets.append({"key": "expense_approvals", "label": "Expenses to approve",
                        "action": "expenses.approve", "count": len(rows), "items": rows})

    # --- Open tickets assigned to me ---
    if has_permission(user, "tickets.manage"):
        rows = await db.tickets.find(
            {"assigned_to": user["id"], "status": "open"}, {"_id": 0}).sort("created_at", 1).to_list(50)
        buckets.append({"key": "my_open_tickets", "label": "Open tickets assigned to me",
                        "action": "tickets.manage", "count": len(rows), "items": rows})

    # --- My leads to follow up (personal pipeline only; full-visibility roles skip this) ---
    if not has_permission(user, "leads.view_all"):
        ids = await visible_lead_ids(user)  # a set of my lead ids (None only for view_all, excluded here)
        followups = []
        if ids:
            docs = await db.leads.find({"id": {"$in": list(ids)}}, {"_id": 0}).to_list(500)
            for l in docs:
                if l.get("status") == "Active" and int(l.get("stage") or 1) < 4:
                    followups.append({
                        "id": l["id"], "full_name": l.get("full_name"), "phone": l.get("phone"),
                        "stage": l.get("stage"), "lifecycle_phase": l.get("lifecycle_phase"),
                        "updated_at": l.get("updated_at"),
                    })
        followups.sort(key=lambda x: x.get("updated_at") or "")
        buckets.append({"key": "my_followups", "label": "Leads to follow up",
                        "action": "leads.edit", "count": len(followups), "items": followups})

    return {"user_id": user["id"], "role": user["role"], "buckets": buckets}

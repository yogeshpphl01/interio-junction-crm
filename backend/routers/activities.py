"""
<module name="routers/activities" layer="api">
  <purpose>Append a timeline entry (Call / Note / etc.) to a lead the caller can
  see, and bump the lead's updated_at (which feeds the recency score signal).</purpose>
  <endpoints>POST /api/activities -> create one activity on a visible lead.</endpoints>
</module>
"""
import uuid
from fastapi import APIRouter, HTTPException, Depends
from core import db, get_current_user, ensure_lead_visible, ActivityInput, now_iso

router = APIRouter()


@router.post("/activities")
async def add_activity(payload: ActivityInput, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": payload.lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await ensure_lead_visible(user, lead)
    doc = {
        "id": str(uuid.uuid4()),
        "lead_id": payload.lead_id,
        "type": payload.type,
        "summary": payload.summary,
        "actor_id": user["id"],
        "created_at": now_iso(),
    }
    await db.activities.insert_one(doc)
    await db.leads.update_one({"id": payload.lead_id}, {"$set": {"updated_at": now_iso()}})
    doc.pop("_id", None)
    doc["actor"] = user
    return doc

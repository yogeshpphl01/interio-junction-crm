"""
<module name="routers/scoring_routes" layer="api">
  <purpose>Transparent lead scoring. Ranks visible leads with a full per-signal
  breakdown, and lets admins persist custom signal weights.</purpose>
  <endpoints>
    GET  /api/scoring           -> ranked leads (optional ?weights= override).
    POST /api/scoring/weights   -> persist weights (admin) in settings.
    GET  /api/scoring/weights   -> current weights (or defaults).
  </endpoints>
  <math>See scoring.compute_score — 6 weighted signals normalised to 0-100.</math>
</module>
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends
from core import (
    db, get_current_user, require_roles, visible_lead_ids,
    WeightsInput, ROLE_ADMIN, ROLE_SALES,
)
from scoring import compute_score, DEFAULT_WEIGHTS
from audit import log_audit

router = APIRouter()


@router.get("/scoring")
async def list_scoring(user: dict = Depends(get_current_user), weights: Optional[str] = None):
    """Return visible leads ranked by score with full signal breakdown."""
    filt: dict = {}
    if user["role"] == ROLE_ADMIN:
        pass
    elif user["role"] == ROLE_SALES:
        filt["assigned_to"] = user["id"]
    else:
        ids = await visible_lead_ids(user)
        filt["id"] = {"$in": list(ids or [])}

    weights_dict = DEFAULT_WEIGHTS.copy()
    if weights:
        try:
            override = json.loads(weights)
            for k in DEFAULT_WEIGHTS:
                if k in override:
                    weights_dict[k] = int(override[k])
        except Exception:
            pass
    else:
        wdoc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
        if wdoc:
            weights_dict = wdoc["value"]

    leads = await db.leads.find(filt, {"_id": 0}).to_list(2000)
    activity_counts: dict[str, int] = {}
    cur = db.activities.aggregate([
        {"$match": {"lead_id": {"$in": [l["id"] for l in leads]}}},
        {"$group": {"_id": "$lead_id", "count": {"$sum": 1}}},
    ])
    async for row in cur:
        activity_counts[row["_id"]] = row["count"]

    enriched = []
    for l in leads:
        s = compute_score(l, activity_counts.get(l["id"], 0), weights_dict)
        enriched.append({
            "lead_id": l["id"],
            "full_name": l["full_name"],
            "lead_type": l["lead_type"],
            "stage": l["stage"],
            "tentative_budget": l["tentative_budget"],
            "score": s["score"],
            "heat": s["heat"],
            "signals": s["signals"],
        })
    enriched.sort(key=lambda x: x["score"], reverse=True)
    return {"weights": weights_dict, "leads": enriched}


@router.post("/scoring/weights")
async def save_weights(payload: WeightsInput, user: dict = Depends(require_roles(ROLE_ADMIN))):
    w = payload.model_dump()
    await db.settings.update_one({"key": "score_weights"}, {"$set": {"value": w}}, upsert=True)
    await log_audit(db, user, "scoring.weights_saved", "settings", "score_weights", "Scoring weights", w)
    return {"weights": w}


@router.get("/scoring/weights")
async def get_weights(user: dict = Depends(get_current_user)):
    wdoc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
    return {"weights": wdoc["value"] if wdoc else DEFAULT_WEIGHTS}

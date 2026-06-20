"""Automation rules, signals, run-checks."""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from core import (
    db, get_current_user, require_roles, DEFAULT_AUTOMATIONS,
    get_automation_state, log_signal, AutomationToggle,
    ROLE_ADMIN,
)
from scoring import compute_score, DEFAULT_WEIGHTS
from audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/automations")
async def list_automations(user: dict = Depends(get_current_user)):
    out = []
    for a in DEFAULT_AUTOMATIONS:
        doc = await db.automations.find_one({"key": a["key"]}, {"_id": 0})
        enabled = doc.get("enabled", a["enabled"]) if doc else a["enabled"]
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        runs = await db.automation_signals.count_documents({"event": a["key"], "created_at": {"$gte": today}})
        out.append({**a, "enabled": enabled, "runs_today": runs})
    return out


@router.patch("/automations/{key}")
async def toggle_automation(key: str, payload: AutomationToggle, user: dict = Depends(require_roles(ROLE_ADMIN))):
    if not any(a["key"] == key for a in DEFAULT_AUTOMATIONS):
        raise HTTPException(status_code=404, detail="Unknown automation")
    await db.automations.update_one({"key": key}, {"$set": {"enabled": payload.enabled}}, upsert=True)
    await log_audit(db, user, "automation.toggled", "automation", key, key, {"enabled": payload.enabled})
    return {"key": key, "enabled": payload.enabled}


@router.post("/automations/run-checks")
async def run_checks(user: dict = Depends(get_current_user)):
    """Run idle-based checks (SLA 48h, escalate hot 24h)."""
    now = datetime.now(timezone.utc)
    cutoff_48 = (now - timedelta(hours=48)).isoformat()
    cutoff_24 = (now - timedelta(hours=24)).isoformat()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    fired = 0
    notify_targets: list[tuple[str, str, dict]] = []

    if await get_automation_state("sla_breach_48h"):
        leads = await db.leads.find({"updated_at": {"$lte": cutoff_48}, "status": "Active"}, {"_id": 0}).to_list(500)
        for l in leads:
            existing = await db.automation_signals.find_one({"event": "sla_breach_48h", "lead_id": l["id"], "created_at": {"$gte": today}})
            if existing:
                continue
            await log_signal("sla_breach_48h", f"SLA breach — {l['full_name']} idle 48h.", l["id"])
            notify_targets.append(("sla_breach_48h", l["id"], {"lead": l}))
            fired += 1

    if await get_automation_state("escalate_hot_lead"):
        wdoc = await db.settings.find_one({"key": "score_weights"}, {"_id": 0})
        weights = wdoc["value"] if wdoc else DEFAULT_WEIGHTS
        leads = await db.leads.find({"status": "Active"}, {"_id": 0}).to_list(2000)
        counts_cur = db.activities.aggregate([
            {"$group": {"_id": "$lead_id", "count": {"$sum": 1}}}
        ])
        counts = {row["_id"]: row["count"] async for row in counts_cur}
        for l in leads:
            s = compute_score(l, counts.get(l["id"], 0), weights)
            if s["score"] >= 80 and l.get("updated_at", "") <= cutoff_24:
                existing = await db.automation_signals.find_one({"event": "escalate_hot_lead", "lead_id": l["id"], "created_at": {"$gte": today}})
                if existing:
                    continue
                await log_signal("escalate_hot_lead", f"Escalated Hot lead {l['full_name']} (score {s['score']}).", l["id"])
                notify_targets.append(("escalate_hot_lead", l["id"], {"lead": l, "score": s["score"]}))
                fired += 1

    await log_audit(db, user, "automation.run_checks", "automation", "run-checks", None, {"fired": fired})

    if notify_targets:
        try:
            from notifications import dispatch_event
            for event, lead_id, payload in notify_targets:
                await dispatch_event(db, event, lead_id, payload)
        except Exception as e:
            logger.warning(f"Notification dispatch failed: {e}")

    return {"fired": fired}


@router.get("/automations/signals")
async def list_signals(user: dict = Depends(get_current_user), limit: int = 50):
    return await db.automation_signals.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)

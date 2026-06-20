"""Command Center analytics."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from core import (
    db, get_current_user, visible_lead_ids,
    STAGES, STAGE_WIN_RATE, ROLE_ADMIN, ROLE_SALES,
)

router = APIRouter()


@router.get("/analytics/command-center")
async def command_center(user: dict = Depends(get_current_user)):
    filt: dict = {}
    if user["role"] == ROLE_ADMIN:
        scope = "company"
    elif user["role"] == ROLE_SALES:
        filt["assigned_to"] = user["id"]
        scope = "self"
    else:
        ids = await visible_lead_ids(user)
        filt["id"] = {"$in": list(ids or [])}
        scope = "self"

    leads = await db.leads.find(filt, {"_id": 0}).to_list(5000)
    total_pipeline = sum(l.get("tentative_budget", 0) for l in leads if l.get("status") == "Active")
    forecast = sum(l.get("tentative_budget", 0) * STAGE_WIN_RATE.get(l.get("stage", 1), 0) for l in leads if l.get("status") == "Active")
    won = [l for l in leads if l.get("status") == "Won"]
    closed = [l for l in leads if l.get("status") in ("Won", "Lost")]
    win_rate = (len(won) / len(closed) * 100) if closed else 0

    cycle_days = 0
    if won:
        diffs = []
        for l in won:
            try:
                c = datetime.fromisoformat(l["created_at"])
                u = datetime.fromisoformat(l["updated_at"])
                diffs.append((u - c).total_seconds() / 86400)
            except Exception:
                pass
        cycle_days = sum(diffs) / len(diffs) if diffs else 0

    funnel = []
    for s in STAGES:
        items = [l for l in leads if l.get("stage") == s["id"] and l.get("status") == "Active"]
        funnel.append({
            "stage": s["id"],
            "name": s["short"],
            "color": s["color"],
            "count": len(items),
            "value": sum(l.get("tentative_budget", 0) for l in items),
        })

    by_source: dict[str, float] = {}
    for l in leads:
        if l.get("status") == "Active":
            by_source[l.get("source", "Other")] = by_source.get(l.get("source", "Other"), 0) + l.get("tentative_budget", 0)
    sources = [{"source": k, "value": v} for k, v in by_source.items()]
    sources.sort(key=lambda x: x["value"], reverse=True)

    months = []
    now = datetime.now(timezone.utc)
    for i in range(6):
        m = now + timedelta(days=30 * i)
        ratio = (i + 1) / 6
        months.append({
            "month": m.strftime("%b %Y"),
            "forecast": round(forecast * ratio, 2),
            "pipeline": round(total_pipeline * (1 - ratio * 0.3), 2),
        })

    return {
        "scope": scope,
        "kpis": {
            "total_pipeline": total_pipeline,
            "forecast": round(forecast, 2),
            "win_rate": round(win_rate, 1),
            "cycle_days": round(cycle_days, 1),
            "active_leads": len([l for l in leads if l.get("status") == "Active"]),
            "won_count": len(won),
        },
        "funnel": funnel,
        "by_source": sources,
        "forecast_trend": months,
    }

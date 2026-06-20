"""Transparent lead scoring engine. Returns 0-100 score with per-signal breakdown."""
from datetime import datetime, timezone
from typing import Any

# Default weights (sum to 100). Each represents the max points a signal can contribute.
DEFAULT_WEIGHTS = {
    "budget_tier": 25,
    "lead_type": 15,
    "source_quality": 10,
    "pipeline_progress": 25,
    "engagement": 15,
    "recency": 10,
}

LEAD_TYPE_RATIO = {
    "Architect": 1.0,
    "Interior Designer": 0.9,
    "Builder": 0.85,
    "Retail Client": 0.6,
}

SOURCE_RATIO = {
    "Architect Partner": 1.0,
    "Referral": 0.9,
    "Website": 0.7,
    "Instagram": 0.6,
    "Google": 0.55,
    "Walk-in": 0.5,
    "Other": 0.4,
}

# stage 1..6 progress ratio; Won = 1.0
STAGE_PROGRESS_RATIO = {1: 0.1, 2: 0.25, 3: 0.45, 4: 0.65, 5: 0.85, 6: 1.0}


def _budget_ratio(budget: float) -> tuple[float, str]:
    # Tiers (INR): <5L=0.3, 5-10L=0.55, 10-25L=0.75, 25-50L=0.9, 50L+=1.0
    if budget >= 50_00_000:
        return 1.0, "≥ 50 Lakh"
    if budget >= 25_00_000:
        return 0.9, "25-50 Lakh"
    if budget >= 10_00_000:
        return 0.75, "10-25 Lakh"
    if budget >= 5_00_000:
        return 0.55, "5-10 Lakh"
    if budget > 0:
        return 0.3, "< 5 Lakh"
    return 0.0, "No budget"


def _recency_ratio(updated_iso: str | None) -> tuple[float, str]:
    if not updated_iso:
        return 0.0, "no activity"
    try:
        if isinstance(updated_iso, str):
            dt = datetime.fromisoformat(updated_iso.replace("Z", "+00:00"))
        else:
            dt = updated_iso
    except Exception:
        return 0.0, "invalid date"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    if hours <= 24:
        return 1.0, f"{hours:.0f}h ago"
    if hours <= 72:
        return 0.75, f"{hours:.0f}h ago"
    if hours <= 168:
        return 0.5, f"{hours/24:.0f}d ago"
    if hours <= 720:
        return 0.25, f"{hours/24:.0f}d ago"
    return 0.05, f"{hours/24:.0f}d ago"


def _engagement_ratio(activity_count: int) -> tuple[float, str]:
    if activity_count >= 10:
        return 1.0, f"{activity_count} activities"
    if activity_count >= 6:
        return 0.75, f"{activity_count} activities"
    if activity_count >= 3:
        return 0.5, f"{activity_count} activities"
    if activity_count >= 1:
        return 0.25, f"{activity_count} activities"
    return 0.0, "no activity"


def compute_score(lead: dict[str, Any], activity_count: int, weights: dict[str, int] | None = None) -> dict:
    """Compute transparent 0-100 score with full signal breakdown."""
    w = weights or DEFAULT_WEIGHTS
    total_w = sum(w.values()) or 1

    b_ratio, b_label = _budget_ratio(float(lead.get("tentative_budget") or 0))
    lt_ratio = LEAD_TYPE_RATIO.get(lead.get("lead_type", ""), 0.5)
    src_ratio = SOURCE_RATIO.get(lead.get("source", ""), 0.4)
    stage = int(lead.get("stage", 1))
    status = lead.get("status", "Active")
    if status == "Won":
        sp_ratio = 1.0
    elif status == "Lost":
        sp_ratio = 0.0
    else:
        sp_ratio = STAGE_PROGRESS_RATIO.get(stage, 0.1)
    eng_ratio, eng_label = _engagement_ratio(activity_count)
    rec_ratio, rec_label = _recency_ratio(lead.get("updated_at"))

    signals = [
        {
            "key": "budget_tier",
            "label": "Budget Tier",
            "raw": b_label,
            "ratio": round(b_ratio, 2),
            "weight": w["budget_tier"],
            "points": round(b_ratio * w["budget_tier"], 1),
        },
        {
            "key": "lead_type",
            "label": "Lead Type",
            "raw": lead.get("lead_type", "—"),
            "ratio": round(lt_ratio, 2),
            "weight": w["lead_type"],
            "points": round(lt_ratio * w["lead_type"], 1),
        },
        {
            "key": "source_quality",
            "label": "Source Quality",
            "raw": lead.get("source", "—"),
            "ratio": round(src_ratio, 2),
            "weight": w["source_quality"],
            "points": round(src_ratio * w["source_quality"], 1),
        },
        {
            "key": "pipeline_progress",
            "label": "Pipeline Progress",
            "raw": f"Stage {stage}/6" + (f" • {status}" if status != "Active" else ""),
            "ratio": round(sp_ratio, 2),
            "weight": w["pipeline_progress"],
            "points": round(sp_ratio * w["pipeline_progress"], 1),
        },
        {
            "key": "engagement",
            "label": "Engagement",
            "raw": eng_label,
            "ratio": round(eng_ratio, 2),
            "weight": w["engagement"],
            "points": round(eng_ratio * w["engagement"], 1),
        },
        {
            "key": "recency",
            "label": "Recency",
            "raw": rec_label,
            "ratio": round(rec_ratio, 2),
            "weight": w["recency"],
            "points": round(rec_ratio * w["recency"], 1),
        },
    ]

    total = sum(s["points"] for s in signals)
    # Normalize to 0-100 in case weights don't sum to 100
    score = round(total * 100 / total_w, 1)
    if score >= 80:
        heat = "Hot"
    elif score >= 60:
        heat = "Warm"
    else:
        heat = "Cold"

    return {"score": score, "heat": heat, "signals": signals, "weights": w}

"""Health + meta endpoints."""
from fastapi import APIRouter
from core import (
    STAGES, LEAD_TYPES, BHK_TYPES, KITCHEN_LAYOUTS, LEAD_SOURCES,
    LEAD_STATUSES, DOC_TYPES, STAGE_WIN_RATE, LEAD_LIFECYCLE_PHASES,
)
from scoring import DEFAULT_WEIGHTS

router = APIRouter()


@router.get("/")
async def root():
    return {"app": "Interio Junction CRM", "status": "ok"}


@router.get("/meta")
async def meta():
    return {
        "stages": STAGES,
        "lead_types": LEAD_TYPES,
        "bhk_types": BHK_TYPES,
        "kitchen_layouts": KITCHEN_LAYOUTS,
        "lead_sources": LEAD_SOURCES,
        "lead_statuses": LEAD_STATUSES,
        "lifecycle_phases": LEAD_LIFECYCLE_PHASES,
        "doc_types": DOC_TYPES,
        "stage_win_rate": STAGE_WIN_RATE,
        "default_weights": DEFAULT_WEIGHTS,
    }

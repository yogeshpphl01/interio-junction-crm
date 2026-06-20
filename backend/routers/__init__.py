"""Routers package. Each module exposes a FastAPI APIRouter."""
from .meta import router as meta_router
from .auth import router as auth_router
from .users import router as users_router
from .leads import router as leads_router
from .measurements import router as measurements_router
from .revisions import router as revisions_router
from .payments import router as payments_router
from .activities import router as activities_router
from .documents import router as documents_router
from .scoring_routes import router as scoring_router
from .automations import router as automations_router
from .analytics import router as analytics_router
from .audit_routes import router as audit_router
from .notifications_routes import router as notifications_router
from .imports import router as imports_router  # NEW: Excel/Meta lead import

ALL_ROUTERS = [
    meta_router, auth_router, users_router, leads_router,
    measurements_router, revisions_router, payments_router,
    activities_router, documents_router, scoring_router,
    automations_router, analytics_router, audit_router, notifications_router,
    imports_router,
]

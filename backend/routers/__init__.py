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
from .roles import router as roles_router      # NEW: account categories (Module 7)
from .fixtures import router as fixtures_router  # NEW: Booking "Fixture" section
from .estimates import router as estimates_router  # NEW: mobile P0 — estimate engine
from .production import router as production_router  # NEW: mobile P0 — Infurnia parts + scan tracking
from .tickets import router as tickets_router        # NEW: mobile P0 — site/production tickets
from .checklists import router as checklists_router  # NEW: mobile P0 — checklists + reconciliation
from .expenses import router as expenses_router      # NEW: mobile P0 — site expenses
from .campaigns import router as campaigns_router    # NEW: mobile P0 — campaign import + MH→PM→SE distribution
from .booking import router as booking_router        # NEW: mobile P0 — booking payment → project activation
from .client import router as client_router          # NEW: mobile P0 — Client App BFF (customer auth + scoped reads)

ALL_ROUTERS = [
    meta_router, auth_router, users_router, leads_router,
    measurements_router, revisions_router, payments_router,
    activities_router, documents_router, scoring_router,
    automations_router, analytics_router, audit_router, notifications_router,
    imports_router, roles_router, fixtures_router, estimates_router, production_router,
    tickets_router, checklists_router, expenses_router, campaigns_router, booking_router,
    client_router,
]

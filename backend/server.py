"""Interio Junction CRM — thin orchestrator. Routers live in /routers."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from core import db
from storage import init_storage
from permissions import refresh_role_cache
from bootstrap import apply_migrations_and_seed
from auth_utils import validate_security_config
from app_check import validate_app_check_config
from routers import ALL_ROUTERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # <startup>
    #   Open the pool, then either run migrations+seed (dev / RUN_MIGRATIONS=1) or,
    #   in production, skip DDL and just load the role cache read-only — so the
    #   serving app can run as a DML-only DB role (ij_app) while migrations run
    #   separately as ij_migrate (python migrate.py). See db/roles.sql.
    # </startup>
    validate_security_config()   # fail fast on missing/weak secrets in production
    validate_app_check_config()  # warn loudly on a misconfigured attestation gate
    await db.connect()
    run_migrations = os.environ.get("RUN_MIGRATIONS", "1").lower() in ("1", "true", "yes", "on")
    if run_migrations:
        await apply_migrations_and_seed()
    else:
        await refresh_role_cache(db)  # read-only: load custom-role permissions
    try:
        init_storage()
    except Exception as e:
        logger.error(f"Storage init error: {e}")
    await _warn_shared_accounts()
    yield
    await db.close()


async def _warn_shared_accounts():
    """Accountability policy (SoD Part 4): flag generic/shared logins so they are
    replaced with named individual accounts (the CEO super-account should be
    break-glass only)."""
    try:
        generic = ("admin@", "ceo@", "info@", "support@", "test@", "tester@")
        rows = await db.users.find({}, {"_id": 0, "email": 1, "role": 1, "is_active": 1}).to_list(1000)
        shared = [r["email"] for r in rows
                  if r.get("is_active", True) and any(str(r.get("email", "")).startswith(g) for g in generic)]
        if shared:
            logger.warning("Account policy: replace generic/shared logins with named accounts -> %s", ", ".join(sorted(shared)))
    except Exception as e:
        logger.debug(f"account policy check skipped: {e}")


app = FastAPI(title="Interio Junction CRM API", lifespan=lifespan)

for r in ALL_ROUTERS:
    app.include_router(r, prefix="/api")


origins_env = os.environ.get("CORS_ORIGINS", "*")
if origins_env == "*":
    cors_origins = ["*"]
    allow_creds = False
else:
    cors_origins = [o.strip() for o in origins_env.split(",")]
    allow_creds = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

# <security-middleware>
#   HTTPS enforcement + security response headers (OWASP ASVS V14.4, Mobile M5;
#   NIST SC-8/SC-23; ISO A.8.20/A.8.24). Behind a TLS-terminating proxy
#   (Cloud Run / load balancer) we trust X-Forwarded-Proto. Enforcement is on
#   only in production so local http dev is unaffected.
# </security-middleware>
_APP_ENV = os.environ.get("APP_ENV", "").lower()
_IS_PROD = _APP_ENV in ("prod", "production")
_ENFORCE_HTTPS = _IS_PROD and os.environ.get("ENFORCE_HTTPS", "1").lower() in ("1", "true", "yes", "on")


@app.middleware("http")
async def security_headers(request, call_next):
    if _ENFORCE_HTTPS:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto != "https":
            return JSONResponse(status_code=403, content={"detail": "HTTPS required"})
    resp = await call_next(request)
    if _IS_PROD:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

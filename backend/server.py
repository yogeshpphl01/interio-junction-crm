"""Interio Junction CRM — thin orchestrator. Routers live in /routers."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from core import db, DEFAULT_AUTOMATIONS
from storage import init_storage
from seed_data import seed_users, seed_leads
from routers import ALL_ROUTERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Interio Junction CRM API")

for r in ALL_ROUTERS:
    app.include_router(r, prefix="/api")


@app.on_event("startup")
async def on_startup():
    # <startup>
    #   1) open the PostgreSQL connection pool, 2) ensure all tables + declared
    #   indexes exist (idempotent CREATE ... IF NOT EXISTS), then 3) run the
    #   original index creation + seed steps unchanged.
    # </startup>
    await db.connect()
    await db.create_all()

    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.leads.create_index("id", unique=True)
    await db.leads.create_index("stage")
    await db.leads.create_index("assigned_to")
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("project_code", unique=True)
    await db.design_revisions.create_index([("project_id", 1), ("revision_number", 1)], unique=True)
    await db.activities.create_index("lead_id")
    await db.stage_history.create_index("lead_id")
    await db.documents.create_index("project_id")
    await db.settings.create_index("key", unique=True)
    await db.automations.create_index("key", unique=True)
    await db.audit_log.create_index([("created_at", -1)])
    await db.audit_log.create_index("action")
    await db.audit_log.create_index("actor_id")

    try:
        init_storage()
    except Exception as e:
        logger.error(f"Storage init error: {e}")

    email_to_id = await seed_users(db)
    await seed_leads(db, email_to_id)

    for a in DEFAULT_AUTOMATIONS:
        if not await db.automations.find_one({"key": a["key"]}):
            await db.automations.insert_one({"key": a["key"], "enabled": a["enabled"]})


@app.on_event("shutdown")
async def shutdown():
    await db.close()


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

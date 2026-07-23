"""
<module name="bootstrap" layer="startup">
  <purpose>
    Schema migration + index creation + seeding — the work that requires DDL
    privileges. Factored out so it can run EITHER on app startup (dev, when
    RUN_MIGRATIONS=1) OR as a one-shot deploy step (`python migrate.py`) under a
    DDL-privileged DB role (ij_migrate), letting the serving app run as a
    DML-only role (ij_app). See docs/security + db/roles.sql (NIST AC-6 / CIS 5).
  </purpose>
</module>
"""
import logging

from core import db, DEFAULT_AUTOMATIONS
from seed_data import seed_users, seed_leads, migrate_pipeline_stages, purge_ceo_logs
from permissions import seed_roles

logger = logging.getLogger(__name__)


async def apply_migrations_and_seed() -> None:
    """Idempotent: create/upgrade the schema, ensure indexes, seed roles/users/data."""
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

    # <rbac>Seed built-in roles + load the permission cache (Module 7).</rbac>
    await seed_roles(db)

    email_to_id = await seed_users(db)
    await migrate_pipeline_stages(db)   # one-time 6->9 stage remap (must precede seeding)
    await seed_leads(db, email_to_id)
    await purge_ceo_logs(db)            # one-time CEO audit-log cleanup

    for a in DEFAULT_AUTOMATIONS:
        if not await db.automations.find_one({"key": a["key"]}):
            await db.automations.insert_one({"key": a["key"], "enabled": a["enabled"]})
    logger.info("Migrations + seed applied")

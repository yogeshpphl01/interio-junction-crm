-- Least-privilege database roles for Interio Junction.
-- NIST 800-53 AC-6 / CIS Control 5 / OWASP: the running app must NEVER be a
-- superuser. Run this ONCE per environment as a DB admin. Replace the :pw
-- placeholders with secrets injected from your secrets manager — never commit
-- real passwords.
--
--   psql "$ADMIN_DSN" \
--     -v migrate_pw="$IJ_MIGRATE_PW" -v app_pw="$IJ_APP_PW" -v ro_pw="$IJ_RO_PW" \
--     -f db/roles.sql
--
-- Then:
--   * migrations  -> DATABASE_URL=postgres://ij_migrate:***@host/ij  python migrate.py
--   * the app     -> DATABASE_URL=postgres://ij_app:***@host/ij  RUN_MIGRATIONS=0  (uvicorn)
--   * reporting/BI-> DATABASE_URL=postgres://ij_readonly:***@host/ij

-- 1) Migration / owner role — owns the schema, may DDL. Used only at deploy.
CREATE ROLE ij_migrate LOGIN PASSWORD :'migrate_pw';
GRANT ALL ON SCHEMA public TO ij_migrate;

-- 2) Application runtime role — DML only, no DDL, no ownership.
CREATE ROLE ij_app LOGIN PASSWORD :'app_pw';
GRANT USAGE ON SCHEMA public TO ij_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ij_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ij_app;

-- 3) Read-only reporting role.
CREATE ROLE ij_readonly LOGIN PASSWORD :'ro_pw';
GRANT USAGE ON SCHEMA public TO ij_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ij_readonly;

-- 4) Tables created later by ij_migrate auto-grant to app + readonly.
ALTER DEFAULT PRIVILEGES FOR ROLE ij_migrate IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ij_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ij_migrate IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ij_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ij_migrate IN SCHEMA public
    GRANT SELECT ON TABLES TO ij_readonly;

-- ij_app owns nothing and cannot CREATE/ALTER/DROP; migrations run as ij_migrate.
-- Consider REVOKE CREATE ON SCHEMA public FROM PUBLIC; on managed Postgres.

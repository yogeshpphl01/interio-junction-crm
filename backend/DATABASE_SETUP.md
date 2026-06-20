<!--
  <doc name="DATABASE_SETUP" audience="operator">
    How to point the Interio Junction CRM backend at your Hostinger PostgreSQL
    database (the one you browse in pgAdmin). Read top-to-bottom once.
  </doc>
-->

# Database setup — PostgreSQL (Hostinger / pgAdmin)

The CRM backend was migrated from MongoDB to **PostgreSQL**. It connects using
**environment variables** — credentials are never committed to the repository.

## 1. Provide the connection details

Set **either** a single connection URL **or** the discrete variables.

### Option A — one URL (recommended)
```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

### Option B — discrete variables
```
PG_HOST=your-host.hostinger.com
PG_PORT=5432
PG_DB=your_database_name
PG_USER=your_db_user
PG_PASSWORD=your_db_password
PG_SSLMODE=require          # Hostinger remote PostgreSQL usually requires SSL
PG_POOL_MAX=10              # optional, connection pool size (default 10)
```

> Put these in `backend/.env` (already git-ignored) for local runs, or in your
> hosting provider's environment-variable settings for production.

## 2. Allow the app server to reach Hostinger

Hostinger blocks remote database connections by default. In hPanel go to
**Databases → Remote PostgreSQL** (or "Remote MySQL/PostgreSQL") and **add the
IP address of the server that runs this backend** to the allow-list. Without
this, connections are refused with a timeout / "no pg_hba.conf entry" error.

## 3. First boot creates everything automatically

On startup the backend:
1. opens a connection pool to your database,
2. runs `CREATE TABLE IF NOT EXISTS …` for every table (see `pg_schema.py`),
3. creates the indexes, and
4. seeds the 4 demo users + sample leads (only if the tables are empty).

After the first boot you will see these tables in **pgAdmin**:

```
users, leads, projects, site_measurements, design_revisions, payments,
activities, stage_history, documents, settings, automations,
automation_signals, audit_log, import_batches
```

Each well-known field is a real, typed column (so you can run normal SQL
reports). A small `extra JSONB` column on every table captures any
not-yet-modeled keys.

## 4. Uploading the leads Excel sheet

1. Log in as **admin** or **sales**.
2. Go to **Leads → Import**.
3. Upload the Meta Lead-Ads `.xlsx` (or `.csv`).

The rows are upserted into the `leads` table. Re-uploading the same file is
safe: leads are matched on the Meta lead id (`meta_lead_id`, unique) and only
their contact/brief fields are refreshed — pipeline stage, status and journey
are preserved. Each run is logged in `import_batches`.

## 5. Lead-journey columns (for your SQL reports)

The `leads` table now carries journey tracking you can query directly:

| Column | Meaning |
|---|---|
| `lifecycle_phase` | Enquiry / In-Progress / Completed / Dropped / On-hold |
| `furthest_stage` | highest pipeline stage (1–6) ever reached |
| `dropped_stage` / `dropped_at` / `dropped_reason` | where & why a lead stopped |
| `delivered_at` | when the project reached factory/delivery |
| `journey` (JSONB) | per-stage entered_at / exited_at timeline |

Example report — count leads by journey bucket:
```sql
SELECT lifecycle_phase, COUNT(*) FROM leads GROUP BY lifecycle_phase;
```

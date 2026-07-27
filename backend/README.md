# Backend — API + database

The **shared brain** behind all four apps: a **FastAPI** service over
**PostgreSQL**. Every app — [`../apps/staff-web`](../apps/staff-web),
[`../apps/customer-web`](../apps/customer-web),
[`../apps/staff-mobile`](../apps/staff-mobile),
[`../apps/customer-mobile`](../apps/customer-mobile) — talks to this one API.

## The dual-BFF

Two front doors on one backend, kept strictly separate:

- **Staff** routes (email/password + MFA/passkeys) issue the `access` token family.
- **Customer** routes under `/api/client/*` (phone + OTP) issue `customer_access`.
- A token from one family is **rejected** on the other's routes. This is the
  backend's core security boundary.

## Layout

```
backend/
├── server.py         app entry: startup (migrations/seed), middleware, router wiring,
│                     the opt-in DPDP retention scheduler
├── routers/          the API surface — one module per area (~34 files):
│                     auth, mfa, client (customer BFF), leads, projects, estimates,
│                     payments, booking, expenses, checklists, chat, privacy,
│                     analytics, audit, users/roles, automations, notifications …
├── core.py           shared dependencies: DB handle, auth guards (require_permission,
│                     step-up), Pydantic models, helpers
├── database.py       async Postgres access layer (Mongo-style API over asyncpg)
├── pg_schema.py      the table definitions (source of truth for columns)
├── auth_utils.py     password hashing, JWTs, TOTP, step-up tokens, cookies
├── permissions.py    RBAC: the permission catalog + role → permission mapping
├── pii_crypto.py     field-level AES-256-GCM encryption + blind index for PII
├── audit.py          hash-chained, tamper-evident audit log
├── retention.py      DPDP storage-limitation sweep (6-month / 10-year, item 8)
├── notifications.py  email + OTP delivery seams (SMTP now; SMS/WhatsApp pluggable)
├── app_check.py      app-attestation gate (Firebase App Check / Play Integrity)
├── bootstrap.py      run migrations + seed demo data on startup
├── storage.py        object storage for documents (signed URLs)
├── db/               SQL helpers (roles, setup)
└── tests/            authz (BOLA/BFLA/dual-BFF), feature and translation tests
```

## Run (standalone)

Usually you run the whole stack with the repo-root `docker compose` (see
[`../DEPLOYMENT.md`](../DEPLOYMENT.md)). To run just the API against a Postgres:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/interio_crm
export JWT_SECRET=$(openssl rand -hex 32)
uvicorn server:app --reload --port 8000     # API at http://localhost:8000/api
```

Security configuration (encryption key, step-up, passkeys, App Check, retention)
is documented in [`../docs/security/`](../docs/security) and `DATABASE_SETUP.md`.

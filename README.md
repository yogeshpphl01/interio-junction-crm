# Interio Junction Applications

The complete software for **Interio Junction** (modular interiors): **four
applications** for two audiences on **two platforms**, all sharing **one backend**
and **one database**.

| Who | Web | Mobile |
|---|---|---|
| **Customers** (your leads & clients) | [`apps/customer-web`](apps/customer-web) | [`apps/customer-mobile`](apps/customer-mobile) |
| **Staff** (your team) | [`apps/staff-web`](apps/staff-web) | [`apps/staff-mobile`](apps/staff-mobile) |

Shared by all four:

- [`backend/`](backend) — the **API + database** (FastAPI + PostgreSQL). One brain
  behind every app.
- [`shared/mobile-core/`](shared/mobile-core) — a shared **Flutter package**
  (`ij_core`) used by both mobile apps (API client, auth, models).

## Repository map

```
interio-junction-applications/
├── apps/
│   ├── customer-web/      React (Vite) — customer portal: phone+OTP login, projects, estimates, payments
│   ├── customer-mobile/   Flutter — the customer app (same features, on the phone)
│   ├── staff-web/         React (Vite) — the staff CRM: pipeline, projects, leads, analytics, admin
│   └── staff-mobile/      Flutter — the staff app: work queue, production/site ops, scanning
├── backend/               FastAPI + PostgreSQL — shared API for all four apps (dual-BFF)
├── shared/
│   └── mobile-core/        Flutter package `ij_core` — shared by both mobile apps
├── docs/                   architecture, security & DPDP, mobile, API contract
├── docker-compose.yml      one command brings up db + backend + both web apps
└── DEPLOYMENT.md           server setup + production hardening
```

Each folder has its **own README** describing what's inside — start there.

## How the pieces fit together (dual-BFF)

Every app talks to the **same backend**, but through **two separate front doors**:

- **Staff** apps authenticate with email + password (+ MFA/passkeys) and use the
  staff API. **Customer** apps authenticate with phone + one-time code and use the
  `/api/client/*` API.
- The two token families are **mutually rejected** — a customer token can't touch
  a staff route, and vice-versa. This is the core security boundary; see
  [`docs/security/`](docs/security).

## Run it

The web half of the system starts with one command (needs Docker):

```bash
docker compose up -d --build
# staff CRM       -> http://YOUR_SERVER_IP/
# customer portal -> http://YOUR_SERVER_IP:8080/
```

Full setup, environment variables, and production hardening:
[`DEPLOYMENT.md`](DEPLOYMENT.md).

> The **two mobile apps** are Flutter and are built separately (they aren't part
> of `docker compose`). See each app's README and
> [`docs/mobile-apps/MOBILE_APPS_OVERVIEW.md`](docs/mobile-apps/MOBILE_APPS_OVERVIEW.md).

## Documentation

| Topic | Where |
|---|---|
| Security controls, DPDP compliance, threat model, ISMS | [`docs/security/`](docs/security) |
| Mobile apps (setup, API contract, push, hardening) | [`docs/mobile-apps/`](docs/mobile-apps) |
| Deploying to a server | [`DEPLOYMENT.md`](DEPLOYMENT.md) |

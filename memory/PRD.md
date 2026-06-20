# Interio Junction CRM — Product Requirements Document

## Original Problem Statement (verbatim)

Production-ready, multi-user Sales CRM for "Interio Junction" — a modular furniture & interior manufacturing company that tracks the full lifecycle of a modular interior project from first enquiry to factory handover. Stack: React + FastAPI + MongoDB. JWT auth with 4 roles, 6 pipeline stages, transparent lead scoring, blueprint stage-gates, workflow automations, and a Command Center analytics dashboard. Warm "workshop-precision" design — bone background, espresso ink, terracotta + walnut accents, Fraunces + Hanken Grotesk typography.

## User Personas

| Persona | Access |
|---|---|
| Admin / CEO | Full visibility: all leads, analytics, revenue, factory handovers, audit log, user management, notifications config |
| Sales Executive | Only their own assigned leads + own pipeline view + own scoring/automations |
| Designer | Only projects with a design revision assigned to them; uploads 2D/3D; updates design status |
| Site Supervisor | Only site visits assigned to them; records measurements + uploads sheets/photos |

## Architecture & Tasks Done

### Iteration 1 (Phases 1–7 MVP) — Feb 2026
- **Phase 1 — Auth + data model + seed**: Full data model with MongoDB collections. JWT (cookies + Bearer fallback). 4 seeded users. 8 sample leads across all 6 stages.
- **Phase 2 — Pipeline Kanban**: 6 columns, native HTML5 drag-and-drop, StageHistory log, auto-create Project on first reach of Site Measurement.
- **Phase 3 — Lead Details**: Stepper, Requirement Brief, Measurements, Revisions, Documents, Payments rail, Activity timeline.
- **Phase 4 — Transparent Lead Scoring**: 0–100 score on 6 weighted signals with live slider + "Why?" expander.
- **Phase 5 — Automations**: Blueprint gates + 4 workflow rules + live signals feed.
- **Phase 6 — Command Center**: KPIs (pipeline, forecast, win rate, cycle), funnel, by-source bar, 6-month forecast.
- **Phase 7 — Polish**: Empty/loading states, mobile responsive, document access control.

### Iteration 2 (Post-MVP enhancements) — Feb 2026
- **Audit log**: Backend `log_audit` helper + comprehensive call sites + admin-only `/api/audit` and `/api/audit/actions` endpoints. Frontend `/audit` page with action filter, search, pagination, color-coded action pills, metadata pills.
- **Lost / Won / On-hold workflow**: `POST /api/leads/{id}/close` endpoint with reason capture (required for Lost). Frontend Close-Lead modal with outcome cards (Won/Lost/On-hold), preset Lost reasons, Won value capture, optional context. Closed banner on Lead Detail. Reopen flow.
- **Email notifications**: SMTP (Hostinger) integration with `/api/notifications/{settings,test}` endpoints. Triggers for SLA-48h, Hot-lead escalation, Revision Requested. Per-event toggles, master switch, admin recipient. Admin-only Notifications page with test-send.
- **Backend refactor**: `server.py` reduced from 1485 → 77 lines. Extracted shared infrastructure to `core.py` (db, constants, models, deps, helpers). Split route handlers into 14 router modules in `/app/backend/routers/`. All paths and contracts preserved.

## Core Requirements (static)

- All API routes prefixed with `/api`
- Role enforcement at the data/query layer, not just UI hiding
- ₹ Lakh / Crore formatting for INR
- Per-stage accent dots from a warm earthy palette
- Indian fonts: Fraunces serif + Hanken Grotesk body
- Default password: `interio2026`

## What's Implemented (cumulative)

- Auth: JWT cookies + Bearer fallback
- RBAC: visible_lead_ids(), ensure_lead_visible(), ensure_project_visible()
- CRUD for leads, measurements, revisions, payments, documents, activities, users
- Stage move with blueprint gate evaluation + admin override
- Lead scoring with persistable default weights (admin-saved)
- Automations with runs_today counter + live signal log + email dispatch
- Analytics endpoint (admin = company scope, others = self scope)
- Audit log with 25+ action types
- Lost/Won/On-hold workflow with reason capture
- SMTP email notifications via Hostinger (master toggle + per-event + admin email + test)
- Frontend pages: Login, Command Center, Pipeline, Lead Detail, Leads list, Site Visits, Lead Scoring, Automations, Settings, Audit, Notifications

## Prioritized Backlog (next iterations)

### P1
- Refresh token rotation on every refresh call
- Bulk lead import (CSV)
- Per-document soft delete with admin restore
- Lost-reason analytics chart on Command Center
- WhatsApp notifications via Twilio (in addition to email)

### P2
- Designer + Supervisor workload dashboard
- Multi-currency support
- White-label theming (per-tenant)
- Auto-assign sales executive by region
- Email digest (daily summary)

### P3
- Mobile native wrapper
- Public client portal for revision approval

## Next Tasks

1. Deploy to production via `deployment_agent`
2. Optional: migrate secrets (JWT_SECRET, SMTP_PASSWORD) from .env to a secret manager
3. Optional: rate-limit `/api/notifications/test` to prevent SMTP abuse

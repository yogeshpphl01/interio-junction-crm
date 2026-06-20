# Interio Junction CRM — Product Requirements Document

## Original Problem Statement (verbatim)

Production-ready, multi-user Sales CRM for "Interio Junction" — a modular furniture & interior manufacturing company that tracks the full lifecycle of a modular interior project from first enquiry to factory handover. Stack: React + FastAPI + MongoDB. JWT auth with 4 roles, 6 pipeline stages, transparent lead scoring, blueprint stage-gates, workflow automations, and a Command Center analytics dashboard. Warm "workshop-precision" design — bone background, espresso ink, terracotta + walnut accents, Fraunces + Hanken Grotesk typography.

## User Personas

| Persona | Access |
|---|---|
| Admin / CEO | Full visibility: all leads, analytics, revenue, factory handovers, user management |
| Sales Executive | Only their own assigned leads + own pipeline view |
| Designer | Only projects with a design revision assigned to them; uploads 2D/3D; updates design status |
| Site Supervisor | Only site visits assigned to them; records measurements + uploads sheets/photos |

## Architecture & Tasks Done (Phases 1–6 + partial Phase 7)

Date: Feb 2026

- **Phase 1 — Auth + data model + seed**: ✅ Full data model with MongoDB collections (users, leads, projects, site_measurements, design_revisions, payments, documents, stage_history, activities, automations, automation_signals, settings). JWT (HTTP-only cookies + Bearer fallback). 4 seeded users. 8 sample leads across all 6 stages.
- **Phase 2 — Pipeline Kanban**: ✅ 6 columns, native HTML5 drag-and-drop with persistence, StageHistory rows, auto-create Project on first reach of Site Measurement.
- **Phase 3 — Lead Details**: ✅ Stepper, Requirement Brief, Site Measurements, Design Revisions (R1/R2/R3 with status + feedback), Documents (uploaded via Emergent object storage), Milestone Payments rail, Activity timeline.
- **Phase 4 — Transparent Lead Scoring**: ✅ 0–100 scoring on 6 weighted signals (budget tier, lead type, source quality, pipeline progress, engagement, recency). Live weight sliders, "Why?" expander showing per-signal points and ratios. Hot/Warm/Cold heat chips on Kanban cards.
- **Phase 5 — Automations**: ✅ Blueprint gates (Site Measurement → Design requires completed measurement; Design → Quotation requires approved revision; Quotation → Factory requires sign-off + ≥50% payments paid). 4 workflow rules (auto-assign supervisor, SLA 48h, notify designer on revision-requested, escalate hot leads at 24h). Live signals feed.
- **Phase 6 — Command Center**: ✅ KPIs (total pipeline, probability-weighted forecast 10/25/45/65/85/100%, win rate, cycle days). Recharts area trend, funnel, pipeline-by-source bar chart.
- **Phase 7 — Polish + deploy (partial)**: ✅ Empty/loading states, form validation, mobile-responsive Kanban + Detail. Object storage with access-controlled download. Deployment pending user request.

## What's Implemented

- Auth: JWT cookies + Bearer fallback, /api/auth/{login,logout,me,refresh}
- RBAC enforced at data layer: visible_lead_ids(), ensure_lead_visible(), ensure_project_visible()
- CRUD for leads, measurements, revisions, payments, documents, activities, users
- Stage move with blueprint gate evaluation + admin override
- Lead scoring with persistable default weights
- Automations with runs_today counter + live signal log
- Analytics endpoint (admin = company scope, others = self scope)
- Frontend: Login, Command Center, Pipeline (drag-drop), Lead Detail, Leads list, Site Visits, Lead Scoring, Automations, Settings

## Core Requirements (static)

- All API routes prefixed with `/api`
- Role enforcement at the data/query layer, not just UI hiding
- ₹ Lakh / Crore formatting for INR
- Per-stage accent dots from a warm earthy palette
- Indian fonts: Fraunces serif + Hanken Grotesk body

## Prioritized Backlog (next iterations)

### P1
- Lost / Won status workflow with reason capture
- Email + WhatsApp notifications (real, not just log)
- Refresh token rotation on every refresh call
- Per-document role enforcement on upload type beyond the current rules
- Audit log page for admins
- Bulk lead import (CSV)

### P2
- Designer / Supervisor workload view
- Multi-currency support
- White-label theming (per-tenant)
- Auto-assign sales executive by region

### P3
- Mobile native wrapper
- Public client portal for revision approval
- WhatsApp inbox

## Next Tasks

1. Refactor server.py into modular routers (auth/leads/projects/scoring/automations/analytics)
2. Add Designer + Supervisor dashboard variants of Command Center
3. Add reason capture when marking lead Lost
4. Persist refresh-token rotation
5. Optionally deploy via `deployment_agent` once user confirms

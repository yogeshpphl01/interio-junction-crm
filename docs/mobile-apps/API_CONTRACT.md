# Interio Junction — Mobile API Contract (P0)

The complete API surface the two mobile apps consume, cross-checked against the
FastAPI routers in `backend/routers/`. This is the spec to build the Flutter
screens against. Companion to `ENTERPRISE_ARCHITECTURE.md` (the *why*); this doc
is the *what* — every endpoint, its auth, and its request/response shape.

- **Client App** → the customer-facing BFF (`routers/client.py`). Customer identity.
- **Company App** → the employee/RBAC surface (the CRM routers). Employee identity.

> **Status:** every endpoint below is implemented and verified end-to-end against
> PostgreSQL. Delivery seams that need external credentials (SMS/WhatsApp OTP,
> FCM push, Razorpay) are stubbed and clearly marked "needs creds".

---

## 1. Base URL & versioning

```
https://<host>/api
```

All paths in this document are relative to `/api` (e.g. `/client/projects` →
`GET https://<host>/api/client/projects`). There is no `/v1` yet; treat this
document as the v1 contract.

---

## 2. The two identity worlds (dual-BFF boundary)

The single biggest security rule. Two JWT families share a signing secret but are
**mutually exclusive** — the `type` claim is checked on every request:

| App | Identity | Access token `type` | Refresh token `type` | Dependency |
|-----|----------|---------------------|----------------------|------------|
| Company App | Employee (`users`) | `access` | `refresh` | `get_current_user` |
| Client App  | Customer (`customers`) | `customer_access` | `customer_refresh` | `get_current_customer` |

- A **customer** token on any Company App endpoint → `401 Invalid token type`.
- An **employee** token on any `/client/*` customer endpoint → `401 Invalid token type`.
- Neither app can ever read the other identity's data. This is enforced centrally,
  not per-route.

**Send the token** as a Bearer header (mobile default):

```
Authorization: Bearer <access_token>
```

(The web CRM also accepts an httpOnly cookie; mobile should always use the header.)

**Token lifetimes**

| Token | TTL |
|-------|-----|
| Employee access | 8 hours |
| Employee refresh | 7 days |
| Customer access | 24 hours |
| Customer refresh | 60 days |

---

## 3. Conventions

- **Errors**: standard FastAPI shape — `{"detail": "<message>"}` with an HTTP
  status. Common codes: `400` validation/guard, `401` unauthenticated / wrong
  token type, `403` authenticated but lacks the permission, `404` not found **or
  not yours** (we return 404 rather than 403 to avoid leaking existence), `409`
  state conflict / idempotent replay.
- **Money**: integers/decimals in the smallest sensible unit are **not** used —
  amounts are plain rupee decimals (e.g. `59000` = ₹59,000, `100300.5`). Currency
  is `"INR"` unless stated.
- **Server-authoritative amounts**: booking amount and estimate totals are always
  computed on the server from line items — never trust a client-sent total.
- **Timestamps**: ISO-8601 UTC strings, second precision (`2026-07-09T10:51:37+00:00`).
- **Idempotency**: booking payment is idempotent per lead (repeat → `409`);
  estimate/design accept and part scans are idempotent (repeat → the same success).
- **IDs**: UUID strings. `project_code` is the human code `IJ-YYYY-NNNN`.

---

## 4. Client App API (`/client/*`)

Customer identity. All routes except the two OTP endpoints require a
`customer_access` Bearer token.

### 4.1 Auth

#### `POST /client/auth/request-otp`  · public
Issue a login code. **Always** returns the same generic body (no phone
enumeration); a code is only generated when the phone matches a lead.
```json
// request
{ "phone": "+91 90000 12345" }
// 200
{ "ok": true, "message": "If your number is registered with us, a login code has been sent." }
```
Policy: 4-digit code, 10-min TTL, 60-second resend cooldown, 5 wrong attempts →
locked. Delivery is stubbed (logged) until an SMS/WhatsApp gateway or Firebase
phone-auth is wired. *(needs creds)*

#### `POST /client/auth/verify-otp`  · public
Verify the code → customer session. Creates the customer on first login and
stamps `customer_id` onto every lead with that phone.
```json
// request
{ "phone": "+91 90000 12345", "code": "1234" }
// 200
{
  "customer": { "id": "…", "full_name": "Neha", "phone": "9000012345",
                "email": null, "is_active": true, "last_login_at": "…", "created_at": "…" },
  "access_token": "…", "refresh_token": "…", "token_type": "bearer"
}
// 400  → { "detail": "Invalid or expired code" }   (bad code, unknown phone, expired, locked)
```

#### `POST /client/auth/refresh`  · public (needs a valid customer refresh token)
```json
{ "refresh_token": "…" }              // → { "access_token": "…", "token_type": "bearer" }
```

#### `POST /client/auth/logout`  · customer
Audit-only (mobile just drops the token). → `{ "ok": true }`

#### `GET /client/me`  · customer
→ `{ "customer": { … } }`

### 4.2 Devices (push)

#### `POST /client/devices`  · customer
```json
{ "token": "<fcm-token>", "platform": "android" }   // → { "ok": true, "device_id": "…" }
```
#### `DELETE /client/devices`  · customer
```json
{ "token": "<fcm-token>" }                            // → { "ok": true }  (deactivates)
```

### 4.3 Home & projects

#### `GET /client/projects`  · customer
The customer's own lead(s) + pipeline stage + project status.
```json
{ "projects": [ {
  "lead_id": "…", "full_name": "Neha", "requirements": "…", "bhk_type": "3 BHK",
  "status": "Active", "lifecycle_phase": "Booking",
  "stage": 4, "stage_name": "Booking", "stage_color": "#7C9082",
  "project": { "project_code": "IJ-2026-0007", "contract_value": 590000,
               "booking_paid": true, "activated_at": "…", "in_production": false }
} ] }
```
`project` is `null` until the booking activates it.

### 4.4 Estimates

#### `GET /client/estimates`  · customer
Only **shared / accepted** estimates (internal drafts never appear), each with
line items.
```json
{ "estimates": [ {
  "id": "…", "version": 1, "status": "shared", "currency": "INR",
  "subtotal": 500000, "discount": 0, "tax": 90000, "total": 590000,
  "valid_until": null, "created_at": "…",
  "items": [ { "id": "…", "description": "Full home interiors", "unit": null,
               "quantity": 1, "rate": 500000, "amount": 500000, "category": null } ]
} ] }
```

#### `POST /client/estimates/{estimate_id}/accept`  · customer
The customer accepts their own **shared** estimate — this is what unlocks the 10%
booking payment. Strictly scoped (someone else's estimate → `404`).
```json
// 200
{ "ok": true, "estimate_id": "…", "status": "accepted" }
// idempotent: re-accepting an accepted estimate → 200 (same body)
// 409 → { "detail": "This estimate is not available to accept" }  (not in 'shared')
```

### 4.5 Designs (the customer feedback loop)

#### `GET /client/designs`  · customer
Shared design revisions (Draft/internal hidden), each with attached
render/CAD/design files (internal manufacturing docs are filtered out).
```json
{ "designs": [ {
  "id": "…", "revision_number": 1, "title": "3D Design v1", "status": "Shared",
  "client_feedback": "", "created_at": "…",
  "documents": [ { "id": "…", "type": "3D Render", "filename": "render.png",
                   "content_type": "image/png", "size": 1000,
                   "storage_path": "…", "created_at": "…" } ]
} ] }
```
Visible revision states: `Shared`, `Approved`, `Revision Requested`.

#### `POST /client/designs/{rev_id}/approve`  · customer
→ `{ "ok": true, "revision_id": "…", "status": "Approved" }` (idempotent).

#### `POST /client/designs/{rev_id}/request-changes`  · customer
Sets the revision to `Revision Requested` and **notifies the designer** (same
automation the CRM uses internally).
```json
{ "feedback": "Please widen the wardrobe." }
// → { "ok": true, "revision_id": "…", "status": "Revision Requested" }
```

### 4.6 Payments & documents

#### `GET /client/payments`  · customer
```json
{
  "summary": { "contract_value": 590000, "paid": 59000, "balance": 531000, "currency": "INR" },
  "payments": [ { "id": "…", "type": "booking", "milestone": "Booking Advance (10%)",
                  "amount": 59000, "currency": "INR", "status": "verified",
                  "method": "manual_upi", "due_date": null, "paid_date": "…" } ]
}
```

#### `GET /client/documents`  · customer
Customer-safe types only (`3D Render`, `2D CAD`, `Design File`, `Quotation PDF`,
`Site Photo`); internal docs and deleted docs are never returned.
```json
{ "documents": [ { "id": "…", "type": "Quotation PDF", "filename": "quote.pdf",
                   "content_type": "application/pdf", "size": 1000,
                   "storage_path": "…", "created_at": "…" } ] }
```
> `storage_path` is a storage reference; the app exchanges it for a signed
> download URL via the storage layer (wired when object storage is configured).

---

## 5. Company App API

Employee identity (`get_current_user`). Each endpoint lists its permission gate;
`—` means any authenticated employee. See §8 for the permission → role mapping.

### 5.1 Auth

| Method | Path | Gate | Notes |
|--------|------|------|-------|
| POST | `/auth/login` | public | `{email,password}` → `{user, access_token, refresh_token}` |
| GET  | `/auth/me` | — | current employee (with `permissions`, `role_label`, `role_color`) |
| POST | `/auth/logout` | — | |
| POST | `/auth/change-password` | — | `{current, new}` |
| POST | `/auth/forgot-password` | public | email OTP reset (generic response) |
| POST | `/auth/reset-password` | public | `{email, otp, new_password}` |
| PATCH| `/auth/profile` | — | edit own profile |
| POST | `/auth/refresh` | public | employee refresh token → new access |

### 5.2 Home feed

#### `GET /me/worklist`  · — (permission-shaped)
The Company App home screen. Buckets are included only for permissions the user
holds, so custom roles get the right home automatically.
```json
{ "user_id": "…", "role": "manager", "buckets": [
  { "key": "estimate_approvals", "label": "Estimates to approve", "action": "estimates.approve",
    "count": 2, "items": [ { "id": "…", "version": 1, "lead_id": "…", "lead_name": "Ravi",
                             "total": 100000, "currency": "INR", "created_at": "…" } ] },
  { "key": "expense_approvals",  "label": "Expenses to approve",  "action": "expenses.approve", "count": 1, "items": [ … ] },
  { "key": "my_open_tickets",    "label": "Open tickets assigned to me", "action": "tickets.manage", "count": 0, "items": [] },
  { "key": "my_followups",       "label": "Leads to follow up",   "action": "leads.edit", "count": 3, "items": [ … ] }
] }
```
Bucket rules: `estimate_approvals`←`estimates.approve`; `expense_approvals`←`expenses.approve`;
`my_open_tickets`←`tickets.manage`; `my_followups`← any role **without** `leads.view_all`
(their active leads at stage < 4).

### 5.3 Leads

| Method | Path | Gate | Notes |
|--------|------|------|-------|
| GET  | `/leads` | — | scoped by visibility (own / all) |
| POST | `/leads` | — | create; body = LeadCreate (see below) |
| GET  | `/leads/{id}` | — | must be visible to you |
| PATCH| `/leads/{id}` | — | |
| POST | `/leads/{id}/move` | — | `{to_stage, note, override}` |
| POST | `/leads/{id}/close` | — | `{status: Won|Lost|On-hold|Active, reason}` |
| POST | `/leads/{id}/check-gate` | — | can this lead advance? |

`LeadCreate`: `{ full_name, phone, lead_type, source, bhk_type, kitchen_layout,
email?, city?, address?, tentative_budget=0, requirements?, assigned_to? }`.

### 5.4 Estimates (`routers/estimates.py`)

Workflow: `draft → submitted → approved → shared → accepted` (+ `submitted →
changes_requested → draft`). Totals computed server-side.

| Method | Path | Gate |
|--------|------|------|
| POST | `/estimates` | `estimates.create` |
| GET  | `/estimates` · `GET /estimates/{id}` | — (visible leads) |
| POST | `/estimates/{id}/submit` | `estimates.create` |
| POST | `/estimates/{id}/approve` | `estimates.approve` |
| POST | `/estimates/{id}/reject` | `estimates.approve` |
| POST | `/estimates/{id}/share` | `estimates.create` (pushes the customer) |
| POST | `/estimates/{id}/accept` | `estimates.create` (or the customer via §4.4) |

Create body:
```json
{ "lead_id": "…", "currency": "INR", "discount": 0, "tax_percent": 18,
  "valid_until": null,
  "items": [ { "description": "Modular kitchen", "quantity": 1, "rate": 500000,
               "unit": null, "category": null, "meta": null } ] }
```
Totals: `subtotal = Σ(qty·rate)`; `total = (subtotal − discount) + tax_percent%`.

### 5.5 Production — Infurnia ingest + QR scan (`routers/production.py`)

We **ingest** Infurnia's parts + QR (we do not generate QR).

| Method | Path | Gate |
|--------|------|------|
| POST | `/cutlists` | `production.manage` — ingest a cut list; idempotent per `part_uid` |
| GET  | `/projects/{id}/parts` | — (production.manage OR project-visible) |
| GET  | `/parts/{part_uid}` | — |
| POST | `/parts/scan` | `production.manage` — advance a part; idempotent per part+station+stage |
| GET  | `/projects/{id}/production-summary` | — |

Ingest body (`CutlistIngestIn`):
```json
{ "project_id": "…", "source": "infurnia", "infurnia_ref": "…", "pdf_ref": "…",
  "parts": [ { "part_uid": "PNL-000123", "name": "Base cabinet side",
               "material": "18mm HDHMR", "dimensions": "720x560", "quantity": 1,
               "qr_value": "<decoded Infurnia QR>" } ] }
```
Scan body (`ScanIn`) — scan **by `part_uid` or `qr_value`**:
```json
{ "part_uid": "PNL-000123", "qr_value": null, "station": "Edge-banding",
  "to_stage": "in_production", "result": "pass", "note": null,
  "photo_ref": null, "device_id": null }
```
`to_stage` ∈ **PART_STAGES**: `ingested, in_production, qc, rework, assembly,
packed, loaded, dispatched, unloaded, installed, ticketed`.

### 5.6 Tickets — site/production issues (`routers/tickets.py`)

| Method | Path | Gate |
|--------|------|------|
| POST | `/tickets` | `tickets.manage` — raise (auto-assigns a PE if none given) |
| GET  | `/tickets` · `/tickets/{id}` | — |
| POST | `/tickets/{id}/media` | — add photo/video |
| POST | `/tickets/{id}/resolve` | `tickets.manage` — `{note, remanufacture}` |

Raise body (`TicketIn`): `{ project_id, kind, title, priority="normal",
description?, part_uid?, assigned_to?, media:[{kind,storage_ref}] }`.
`kind` ∈ **`damaged` | `missing` | `fitting`**. If `remanufacture:true` on resolve
and a `part_uid` is linked, that part is sent back to production (`rework`).

### 5.7 Checklists + reconciliation (`routers/checklists.py`)

| Method | Path | Gate |
|--------|------|------|
| POST | `/checklists` | `production.manage` OR `installation.manage` |
| GET  | `/checklists` · `/checklists/{id}` | — |
| POST | `/checklists/{id}/items` | add an item |
| PATCH| `/checklists/{id}/items/{item_id}` | `{checked, photo_ref, note}` |
| POST | `/checklists/{id}/complete` | e-sign `{signature_ref}` |
| GET  | `/projects/{id}/loading-reconciliation` | the headline load/unload check |

Create body: `{ project_id, type, items:["label", …] }`. `type` ∈ **`factory`,
`pack`, `load`, `unload`, `install`, `closure`**. Reconciliation compares parts
scanned `loaded/dispatched` vs `unloaded/installed` and flags missing/short-shipped.

### 5.8 Expenses (`routers/expenses.py`)

Separation of duties: submitter ≠ approver.

| Method | Path | Gate |
|--------|------|------|
| POST | `/expenses` | `expenses.submit` — `{project_id, amount, currency="INR", note?, bill_photo_ref?}` |
| GET  | `/expenses` | — (filter `?status=`) |
| POST | `/expenses/{id}/approve` | `expenses.approve` |
| POST | `/expenses/{id}/reject` | `expenses.approve` |

### 5.9 Campaigns + distribution (`routers/campaigns.py`)

The Marketing-Head → Project-Manager → Sales-Executive lead funnel.

| Method | Path | Gate |
|--------|------|------|
| POST | `/campaigns/import` | `leads.upload_excel` — Excel/CSV upload → undistributed pool |
| GET  | `/campaigns` | — |
| POST | `/campaigns/{id}/distribute` | `leads.distribute` — round-robin to PMs |
| POST | `/leads/distribute-to-se` | `leads.assign` — PM → SEs (`auto_equal` or manual) |

### 5.10 Booking payment → activation (`routers/booking.py`)

#### `POST /leads/{lead_id}/booking-payment`  · `payments.manage`
The system pivot. Verified 10% payment activates the project. Idempotent per lead.
```json
// request (amount optional; server derives 10% of the accepted estimate)
{ "method": "manual_upi", "reference": "UPI-TXN-0001", "screenshot_ref": null, "amount": null }
// 200
{ "activated": true, "lead_id": "…", "stage": 4,
  "project_id": "…", "project_code": "IJ-2026-0007",
  "payment": { "id":"…","type":"booking","amount":59000,"status":"verified", … },
  "group_creation_pending": true }
// 409 → already recorded · 400 → no accepted estimate · 403 → lacks payments.manage
```
Same `on_payment_received()` path serves manual-UPI now and Razorpay later.

### 5.11 Other CRM surfaces the app reuses

| Area | Endpoints | Gate |
|------|-----------|------|
| Measurements | `POST /measurements`, `PATCH /measurements/{id}`, `GET /measurements` | `measurements.manage` |
| Design revisions | `POST /revisions`, `PATCH /revisions/{id}` | `revisions.manage` |
| Documents | `POST /documents`, `GET /documents/{id}/download` | `documents.upload` |
| Milestone payments | `POST /payments`, `PATCH /payments/{id}` | `payments.manage` |
| Devices (employee push) | `POST /devices`, `DELETE /devices` | — |

---

## 6. Push notifications

Registration is per-app (§4.2 customer, §5.11 employee). One `send_push` seam
fans a message out to all of an owner's live devices and records the outcome on
the audit log (`notification.sent` / `notification.failed`, channel `push`).

**Wired events (P0)** — both push the customer, guarded by the lead's `customer_id`:

| Trigger | Title |
|---------|-------|
| Estimate shared (`/estimates/{id}/share`) | "New estimate to review" |
| Booking activated (`/leads/{id}/booking-payment`) | "Booking confirmed 🎉" |

Delivery is stubbed (logged) until FCM credentials are set — going live is a
one-function change in `push._deliver_push()`. *(needs creds)*

---

## 7. FCM payload (when live)

```json
{ "notification": { "title": "New estimate to review", "body": "…" },
  "data": { "type": "estimate", "estimate_id": "…" } }
```
`data.type` values the app deep-links on: `estimate`, `booking` (more added as
events are wired).

---

## 8. Permission → role reference

28 permission keys, 8 built-in roles. Gates above name the key; this maps keys to
the roles that hold them (custom roles can hold any subset).

| Key (used by mobile) | Roles holding it |
|----------------------|------------------|
| `estimates.create` | Sales Executive |
| `estimates.approve` | Project Manager, Marketing Head |
| `payments.manage` | Sales Executive (+ admins) |
| `production.manage` | Production Engineer |
| `tickets.manage` | Site Manager, Production Engineer, Project Manager, Marketing Head |
| `installation.manage` | Site Manager |
| `expenses.submit` | Site Manager |
| `expenses.approve` | Project Manager, Marketing Head |
| `leads.upload_excel` | Marketing Head |
| `leads.distribute` | Marketing Head |
| `leads.assign` | Project Manager, Marketing Head |
| `leads.view_all` | Project Manager, Marketing Head (+ admins) |

CEO/Admin hold all keys (Admin lacks only `users.delete`). Labels: `manager` →
"Project Manager", `supervisor` → "Site Manager".

---

## 9. Enums quick reference

- **Pipeline stages (1–9)**: Leads, Initial Estimate, Consultation, **Booking (4)**,
  Site Measurement, Design, Production Design, Revised Estimate, Factory Production.
- **Estimate status**: `draft, submitted, approved, shared, accepted, changes_requested`.
- **Revision status**: `Draft, Shared, Approved, Revision Requested` (customer sees the last three).
- **Part stages**: `ingested, in_production, qc, rework, assembly, packed, loaded, dispatched, unloaded, installed, ticketed`.
- **Ticket kind**: `damaged, missing, fitting`. **Checklist type**: `factory, pack, load, unload, install, closure`.
- **Payment status**: `pending, verified` (verified = money received).

---

## 10. Open items (needed to go fully live)

1. **Infurnia QR payload sample** — confirm the exact decoded `qr_value` format on a
   real panel label so `/parts/scan` matching is 1:1 (currently a 1-line adapter).
2. **Pricing engine** — the owner's estimate Excel replaces placeholder line-item
   rates in the estimate builder.
3. **Razorpay credentials** — flip booking payment from manual-UPI verify to online
   (order → checkout → webhook), reusing the same activation path
   (`docs/mobile-apps/payments/razorpay_booking.reference.py`).
4. **FCM credentials** — activate real push (`push._deliver_push`).
5. **SMS/WhatsApp or Firebase phone-auth** — activate real OTP delivery; on Firebase,
   only the `verify-otp` step changes (swap the code check for ID-token verification).
6. **Chat** — customer↔team messaging is Firestore-native (real-time) and lands with
   the app track, not this REST surface.

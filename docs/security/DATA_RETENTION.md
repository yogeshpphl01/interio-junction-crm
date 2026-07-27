# Data classification, retention & DPDP data-subject rights

Aligns with **India DPDP Act 2023** (§6 consent, §8(7) retention, §11–13 data-
principal rights), ISO/IEC **27701**, ISO/IEC **27018**, NIST **SC-28**.

## 1. Data classification

| Class | Examples | Handling |
|---|---|---|
| **Sensitive PII** | customer phone, email, name, address; staff recovery email | Encrypt in transit (TLS) + at rest; access-logged; least-privilege. **Field-level encryption for customer phone/email is implemented** (AES-GCM + blind index, env-gated `PII_ENCRYPTION_KEY`, C6). |
| **Financial** | payments, estimates, contract value, UPI/gateway refs | Retained for tax/legal; restrict who can query; four-eyes on confirm (P1-9). |
| **Operational** | leads, projects, measurements, revisions, tickets, checklists | Business records; PII within them is de-identified on erasure. |
| **Authentication** | password hashes, TOTP secrets, backup codes, OTP rows, tokens | Never logged; hashed/short-lived; `token_version` revocation. |
| **Audit** | immutable action log | Append-only; retained for accountability; never edited. |

## 2. Retention schedule (enforced by the retention engine)

| Data | Retention | Purge mechanism |
|---|---|---|
| **Enquiry-only leads** (never started a project) | **6 months** from last engagement | **Auto-anonymize** by the retention sweep, after a **7-day advance notice**; re-engaging (any update) resets the clock (`backend/retention.py`) |
| **Project clients** | **10 years** from delivery (warranty + legal) | Flagged for staff **review** after 10 years — never auto-erased (a human decides) |
| Customer/staff OTP rows (`customer_otps`, `password_resets`) | consumed or ~24h | short TTL; consumed-flag; candidate purge job |
| Auth/session tokens | TTL (access 8–24h, refresh 7–60d) | expiry + `token_version` revocation |
| Closed/cancelled projects | per tax law (e.g. 8 years for financial) | archive; de-identify PII when no longer needed |
| Audit log | ≥ the longest legal retention | retained; append-only; never deleted |
| Uploaded documents | project lifetime + legal retention | delete bytes on erasure where not legally required |

**Retention engine (item 8, `backend/retention.py`).** A daily, opt-in sweep
(`RETENTION_SWEEP_ENABLED`) that: (1) sends the 7-day advance notice to enquiry
leads crossing the 6-month line; (2) anonymizes those whose notice is ≥7 days old
— so a lead is **never erased without a prior warning**; (3) flags 10-year project
clients for review. Idempotent, absolute-cutoff driven, fully audited
(`retention.notice_sent` / `retention.erased` / `retention.review_due`). Staff can
dry-run it (`GET /api/retention/preview`) or run it on demand
(`POST /api/retention/run`, step-up required) from the **Privacy** page.

> Windows are the implemented defaults, overridable via
> `RETENTION_ENQUIRY_DAYS` / `RETENTION_PROJECT_DAYS` / `RETENTION_NOTICE_DAYS`.
> **Confirm with a CA/lawyer** for Indian tax (Income Tax Act / GST) and DPDP
> purpose-limitation. DPDP §8(7): erase personal data once the purpose is served
> and retention is not legally required.

## 3. Data-principal (customer) rights — how they are served

| Right (DPDP) | Endpoint | Notes |
|---|---|---|
| **Consent** §6 (grant/withdraw) | `POST /api/client/me/consent`, `GET …/consent` | itemized catalog: **service** (necessary, cannot be withdrawn), **ai_training**, **analytics**, **marketing** (all optional, default OFF). AI training is a **separate declinable opt-in** (purpose limitation). Choices logged with the policy version. |
| **Access / portability** §11 | `GET /api/client/me/export` | structured JSON of all data we hold about them |
| **Correction** §12 | `POST /api/client/me/change-contact` (+ `/verify`) | self-service email/phone change, verified by an OTP to the **new** value (item 9); staff can also correct records |
| **Erasure** §13 | Enquiry-only: `POST /api/client/me/erasure-request` erases **immediately** (item 10). Project clients: same request is **queued** → staff `POST /api/customers/{id}/erase` | staff action anonymizes PII across the customer + linked leads, revokes sessions, and **retains transactional/tax records** per §8(7). Staff erase requires account-management rights + step-up; fully audited. |

Erasure **de-identifies** rather than hard-deletes: `full_name → "[erased]"`,
`phone`/`email → unique redacted tokens`, `is_active=false`, `erased_at` stamped,
sessions revoked. Leads/estimates/payments rows are kept (financial retention)
but no longer carry personal data.

## 4. Processors & cross-border transfers (DPDP §8(2))

Maintain a Data Processing Agreement (DPA) with each processor and record where
data is stored/processed:

| Processor | Purpose | DPA | Region |
|---|---|---|---|
| Cloud host / DB | app + database | ☐ | … |
| Object storage | document bytes | ☐ | … |
| FCM (Google) | push notifications | ☐ | … |
| Payment gateway (Razorpay) | booking payments | ☐ | … |
| SMS/WhatsApp provider | OTP + updates | ☐ | … |

## 5. Privacy policy & store disclosures (M4)

- Publish a privacy policy (purposes, data classes, retention, rights, contact).
- Complete Google Play **Data Safety** and Apple **Privacy Nutrition** labels to
  match what the apps actually collect (phone, name, photos for site/QC, tokens).

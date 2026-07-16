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

## 2. Retention schedule (set concrete values before go-live)

| Data | Retention | Purge mechanism |
|---|---|---|
| Customer/staff OTP rows (`customer_otps`, `password_resets`) | consumed or 24h | scheduled purge job (candidate) |
| Auth/session tokens | TTL (access 8–24h, refresh 7–60d) | expiry + `token_version` |
| Leads that never convert | e.g. 24 months of inactivity | review + anonymize |
| Closed/cancelled projects | per tax law (e.g. 8 years for financial) | archive; de-identify PII when no longer needed |
| Audit log | ≥ the longest legal retention | retained; never deleted |
| Uploaded documents | project lifetime + legal retention | delete bytes on erasure where not legally required |

> These are **defaults to confirm with a CA/lawyer** for Indian tax (Income Tax
> Act / GST) and DPDP purpose-limitation. DPDP §8(7): erase personal data once
> the purpose is served and retention is not legally required.

## 3. Data-principal (customer) rights — how they are served

| Right (DPDP) | Endpoint | Notes |
|---|---|---|
| **Consent** §6 (grant/withdraw) | `POST /api/client/me/consent`, `GET …/consent` | append-only ledger; purposes: data_processing, marketing, whatsapp_updates |
| **Access / portability** §11 | `GET /api/client/me/export` | structured JSON of all data we hold about them |
| **Correction** §12 | existing profile edits + staff update | name/phone/email corrections |
| **Erasure** §13 | `POST /api/client/me/erasure-request` → staff `POST /api/customers/{id}/erase` | request is lodged by the customer; staff action anonymizes PII across the customer + linked leads, revokes sessions, and **retains transactional/tax records** per §8(7). Requires account-management rights + step-up; fully audited. |

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

# PII security & handling standard (item 1)

How Interio Junction identifies, minimizes, protects and disposes of personal data
across the four apps and the shared backend. Aligns with **DPDP Act 2023**,
ISO/IEC **27701**, ISO/IEC **27018**, NIST **SC-8/SC-28/AC**, OWASP ASVS.

> **Not legal advice.** Engineering standard; have a qualified Indian privacy
> lawyer review the classification and retention before go-live.

Related: [`DATA_RETENTION.md`](DATA_RETENTION.md) ·
[`DPDPA_COMPLIANCE.md`](DPDPA_COMPLIANCE.md) ·
[`INFORMATION_SECURITY_POLICY.md`](INFORMATION_SECURITY_POLICY.md) ·
[`THREAT_MODEL.md`](THREAT_MODEL.md).

---

## 1. What is PII here (data inventory)

| Category | Fields | Where | Subject |
|---|---|---|---|
| Contact | name, phone, email, address, city | `leads`, `customers`, `users.recovery_email`/`phone` | customer, staff |
| Project | requirements, BHK/layout, measurements, site photos, design revisions | `leads`, `projects`, `documents` | customer |
| Financial | estimates, payments, contract value, gateway/UPI refs | `estimates`, `payments`, `bookings` | customer |
| Authentication | password hashes, TOTP secrets, passkey public keys, backup codes, OTP rows, tokens | `users`, `customer_otps`, `password_resets` | staff, customer |
| Behavioural | pipeline stage, activity, audit trail | `leads.journey`, `audit_log` | customer, staff |

The **audit log** intentionally records *actions on* PII (who erased whom), not
PII payloads.

## 2. Classification → handling

| Class | Examples | Minimum handling |
|---|---|---|
| **Sensitive PII** | phone, email, name, address | TLS in transit; **field-level AES-256-GCM at rest** for customer phone/email (`pii_crypto.py`, env-gated `PII_ENCRYPTION_KEY`); least-privilege; access-audited |
| **Financial** | payments, refs | tax/legal retention; restricted roles; four-eyes on confirm/refund + step-up |
| **Authentication** | hashes, secrets, OTPs | **never logged**; bcrypt password hashes; TOTP secret flagged encrypt-at-rest; OTPs hashed + short-TTL; `token_version` instant revocation |
| **Operational** | leads, projects | business records; PII de-identified on erasure/retention |

## 3. Core controls

- **Encryption in transit.** HTTPS enforced in production (HSTS, redirect); mobile
  refuses non-HTTPS bases in release builds and supports cert pinning.
- **Encryption at rest for PII.** `pii_crypto.py` — AES-256-GCM per-field with a
  deterministic **blind index** so uniqueness/lookups on phone/email still work
  without storing plaintext. Key derived from `PII_ENCRYPTION_KEY`; load from a
  KMS/Secret Manager (envelope encryption) in production (see
  [`SECRETS.md`](SECRETS.md)).
- **Data minimization.** Each purpose collects only what it needs; optional
  purposes default **off**; export/erasure operate on a known, enumerated set.
- **Least privilege.** Permission-gated access (`permissions.py`); customer vs
  staff are separate token families (dual-BFF) that are mutually rejected.
- **No PII in logs.** OTP codes and reset codes are logged only when
  `OTP_DEBUG_LOG=1` (dev); production logs mask to the last 4 digits. Auth
  secrets are never logged.
- **PII in flight to processors.** SMS/WhatsApp, email, push (FCM), payment
  gateway — each needs a DPA and a recorded region (see `DATA_RETENTION.md §4`).

## 4. Access, correction, export, erasure (data-subject rights)

Implemented end-to-end — see `DATA_RETENTION.md §3` for the endpoint table.
Highlights: self-service **export** (`/client/me/export`), **correction** of
email/phone via OTP-to-new-value (`/client/me/change-contact`), **erasure**
(immediate for enquiry-only, queued for project clients), and consent that treats
**AI-model training as a separate, declinable opt-in**.

## 5. Disposal

Erasure and the retention engine **de-identify** rather than hard-delete so that
statutory transactional records survive (DPDP §8(7)): `full_name → "[erased]"`,
`phone`/`email → unique redacted tokens`, sessions revoked, `erased_at`/
`retention_erased_at` stamped. Document bytes are deleted where not legally
required.

## 6. Breach handling

A PII breach follows [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md): contain,
assess, **notify the Data Protection Board and affected principals without undue
delay (72h target)**, remediate, post-mortem.

## 7. Responsibilities

| Role | PII responsibility |
|---|---|
| Data Protection / security lead | owns this standard, the inventory and DPA register; grievance/breach point |
| Engineering | keep encryption, minimization, logging hygiene and rights-endpoints correct; no PII in new logs |
| Staff (admins) | action erasure/retention correctly; never export PII outside the system |

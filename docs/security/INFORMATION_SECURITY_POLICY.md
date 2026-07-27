# Information security policy (item 3)

The organisation-level rules for protecting Interio Junction's systems and data.
This is the parent policy; the [`ISMS.md`](ISMS.md) governs how it is run and
reviewed, and the topic standards below carry the detail. Aligned to ISO/IEC
**27001 Annex A**, NIST **800-53**, OWASP **ASVS**, and the **DPDP Act 2023**.

> **Not legal advice.** Adapt ownership, cadence and legal retention with
> qualified advisers before go-live.

## 1. Purpose & scope

Protect the **confidentiality, integrity and availability** of the CRM backend,
database, the four apps (customer & staff, mobile & web), and the personal data
they process. Applies to all staff, contractors and processors.

## 2. Principles

1. **Least privilege & need-to-know** — access is granted by role/permission, not
   by default.
2. **Defense in depth** — no single control is trusted alone.
3. **Secure by default** — safe defaults; risky features are opt-in and gated.
4. **Privacy by design** — see [`PRIVACY_BY_DESIGN.md`](PRIVACY_BY_DESIGN.md).
5. **Accountability** — privileged actions are attributable and audited.

## 3. Control domains (policy → where it lives)

| Domain | Policy | Implementation |
|---|---|---|
| **Access control** | Named accounts; RBAC; MFA for staff; separation of duties; break-glass CEO account alerted | `permissions.py`, TOTP MFA + passkeys, step-up on sensitive actions, dual-BFF token isolation, four-eyes on finance |
| **Authentication** | Strong auth; lockout; no shared logins | password bcrypt + login lockout; **change-password lockout → email+phone OTP reset (item 11)**; customer phone-OTP; passkeys/WebAuthn |
| **Cryptography** | TLS everywhere; encrypt sensitive data at rest; manage keys in a KMS | HSTS + HTTPS enforcement; **AES-256-GCM field encryption** (`pii_crypto.py`); cert pinning (mobile); see [`SECRETS.md`](SECRETS.md) |
| **Logging & monitoring** | Security-relevant events logged; logs tamper-evident; no secrets in logs | **hash-chained audit log** (`audit.py`, `/audit/verify-chain`); OTP/secret redaction |
| **Data protection** | Classify, minimize, retain, dispose | [`PII_HANDLING.md`](PII_HANDLING.md), [`DATA_RETENTION.md`](DATA_RETENTION.md), retention engine |
| **Secure development** | Review, dependency & secret scanning, threat modeling | [`SECURITY_CI.md`](SECURITY_CI.md), [`THREAT_MODEL.md`](THREAT_MODEL.md), branch review |
| **Mobile** | Platform hardening | [`MOBILE_SECURITY_STANDARDS.md`](MOBILE_SECURITY_STANDARDS.md) — App Check/attestation, secure storage, screen protection, cert pinning |
| **Vulnerability mgmt** | Patch on a risk-based SLA; scan dependencies | CI dependency/secret scans; track and remediate |
| **Vendor/processor** | DPA + region recorded before data flows | `DATA_RETENTION.md §4` register |
| **Incident response** | Defined roles; DPDP 72h breach notification | [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md) |
| **Resilience** | Backup & tested restore; DR objectives | [`BACKUP_DR.md`](BACKUP_DR.md) |

## 4. Acceptable use (essentials)

- Use named accounts; never share credentials; enrol MFA (staff).
- Access personal data only for a legitimate work purpose.
- Never copy PII out of the system (spreadsheets, personal email, chat).
- Report suspected incidents immediately per `INCIDENT_RESPONSE.md`.

## 5. Enforcement & exceptions

Violations may lead to access revocation and disciplinary action. Exceptions are
time-boxed, risk-assessed, approved by the security lead, and recorded in the
ISMS risk register.

## 6. Review

Reviewed at least **annually** and after any major change or significant incident
(see `ISMS.md`).

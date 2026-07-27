# Information Security Management System (ISMS) (item 4)

A lightweight, ISO/IEC **27001**-aligned management system sized for Interio
Junction — how security is **governed, measured and improved**, not just the
controls themselves. It ties together the policy and standards in this folder.

> **Not legal advice / not a certification.** This is an operating framework you
> can grow into a formal ISMS. Have scope, roles and legal retention reviewed by
> qualified advisers.

## 1. Scope

The CRM backend (FastAPI + PostgreSQL), the four applications (customer & staff ×
mobile & web), their infrastructure, and the personal + business data they
process. Boundaries and data flows: [`THREAT_MODEL.md`](THREAT_MODEL.md) and the
architecture diagrams in this folder.

## 2. Roles & responsibilities

| Role | Responsibility |
|---|---|
| **Management / owner** | Approves policy, funds remediation, owns residual risk |
| **Security / Data Protection lead** | Runs the ISMS, risk register, DPA register; grievance + breach contact (DPDP) |
| **Engineering** | Builds & maintains controls; secure SDLC; fixes findings |
| **Staff (admins)** | Operate access, erasure and retention correctly |
| **Processors** | Contractual security via DPAs |

## 3. Policy & standards set (this folder)

| Document | Covers |
|---|---|
| [`INFORMATION_SECURITY_POLICY.md`](INFORMATION_SECURITY_POLICY.md) | Parent policy, control domains, acceptable use (item 3) |
| [`PII_HANDLING.md`](PII_HANDLING.md) | PII inventory, classification, protection, disposal (item 1) |
| [`SECURITY_BY_DESIGN.md`](SECURITY_BY_DESIGN.md) | Engineering principles (item 5) |
| [`PRIVACY_BY_DESIGN.md`](PRIVACY_BY_DESIGN.md) | 7 foundational PbD principles (item 7) |
| [`DPDPA_COMPLIANCE.md`](DPDPA_COMPLIANCE.md) | DPDP mapping, consent, rights (items 2, 8, 9, 10) |
| [`DATA_RETENTION.md`](DATA_RETENTION.md) | Classification + retention schedule + rights |
| [`THREAT_MODEL.md`](THREAT_MODEL.md) | Assets, threats (STRIDE), trust boundaries |
| [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md) | Breach handling incl. DPDP 72h |
| [`BACKUP_DR.md`](BACKUP_DR.md) | Backup & disaster recovery |
| [`MOBILE_SECURITY_STANDARDS.md`](MOBILE_SECURITY_STANDARDS.md) | Mobile hardening |
| [`SECRETS.md`](SECRETS.md) · [`SECURITY_CI.md`](SECURITY_CI.md) | Secret/key management · secure pipeline |

## 4. Asset register (starter)

| Asset | Type | Owner | Sensitivity |
|---|---|---|---|
| PostgreSQL database | Data store | Eng | High (PII + financial) |
| Backend API service | Application | Eng | High |
| Customer/staff apps | Client | Eng | Medium |
| Secrets (JWT, PII key, SMTP, gateway) | Credential | Sec lead | Critical |
| Audit log | Record | Sec lead | High (integrity) |
| Object storage (documents) | Data store | Eng | Medium/High |

## 5. Risk register (method + starter entries)

Risk = likelihood × impact; treat by **mitigate / accept / transfer / avoid**;
track owner and status. Review quarterly and on change.

| # | Risk | Existing controls | Treatment |
|---|---|---|---|
| R1 | Credential theft / account takeover | MFA, passkeys, login + change-password lockout, step-up, `token_version` revocation | Mitigated; monitor |
| R2 | PII disclosure (DB/log leak) | Field-level encryption, no-PII logging, least privilege, dual-BFF | Mitigated; add KMS envelope |
| R3 | Privilege abuse / insider | RBAC, four-eyes finance, tamper-evident audit chain | Mitigated; periodic access review |
| R4 | Over-retention of PII | Retention engine (6mo/10yr), erasure | Mitigated; confirm legal windows |
| R5 | Vendor/processor exposure | DPA register, region recording | In progress — complete DPAs |
| R6 | Data loss / outage | Backups + tested restore, DR objectives | Mitigate; schedule restore drills |
| R7 | Vulnerable dependencies | CI dependency + secret scans | Mitigated; keep SLAs |

## 6. Operate → check → improve (PDCA)

- **Plan:** maintain scope, risk register, control objectives.
- **Do:** operate the controls above; onboard/offboard access promptly.
- **Check (metrics):** MFA enrolment %, open findings by severity & age, audit
  chain verification pass, backup-restore test result, mean time to remediate,
  DPDP requests served within SLA (≤30 days), incidents.
- **Act:** feed findings, incidents and audit results into the register; fix;
  re-review.

## 7. Review cadence

| Activity | Frequency |
|---|---|
| Risk register review | Quarterly + on major change |
| Access review (least privilege) | Quarterly |
| Policy/standards review | Annually |
| Backup restore drill | Semi-annually |
| Audit-chain verification | Continuous/On-demand (`/audit/verify-chain`) |
| Management review of ISMS | Annually + post-incident |

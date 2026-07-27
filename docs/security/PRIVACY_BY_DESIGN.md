# Privacy by design (item 7)

Privacy is a default property of the system, not a setting the user must find.
This maps the **7 foundational principles of Privacy by Design** (Cavoukian) to
concrete controls in Interio Junction, and to the **DPDP Act 2023**.

Related: [`DPDPA_COMPLIANCE.md`](DPDPA_COMPLIANCE.md) ·
[`PII_HANDLING.md`](PII_HANDLING.md) · [`DATA_RETENTION.md`](DATA_RETENTION.md) ·
[`SECURITY_BY_DESIGN.md`](SECURITY_BY_DESIGN.md).

> **Not legal advice.** Have the consent notice, retention and grievance process
> reviewed by a qualified Indian privacy lawyer before go-live.

## The 7 principles → how we implement them

| # | Principle | Implementation |
|---|---|---|
| 1 | **Proactive, not reactive** | Retention engine erases stale enquiry data automatically after a notice; optional consents are off until chosen; threat-modeling precedes new surfaces |
| 2 | **Privacy as the default** | Only **necessary** processing (service) is on by default; **ai_training, analytics, marketing default OFF**; a fresh visitor is in the most private state |
| 3 | **Privacy embedded into design** | Consent catalog, export, correction and erasure are first-class API + UI in all four apps — not bolt-ons; dual-BFF isolates customer data from staff tooling |
| 4 | **Full functionality (positive-sum)** | Declining AI-training/analytics/marketing does **not** reduce the core service; the app works fully on necessary consent alone |
| 5 | **End-to-end security** | TLS in transit; AES-256-GCM PII at rest; least privilege; tamper-evident audit; secure disposal via de-identification (see [`SECURITY_BY_DESIGN.md`](SECURITY_BY_DESIGN.md)) |
| 6 | **Visibility & transparency** | Plain-language consent notice with a **policy version**; itemized purposes; choices logged; users can see and change consent anytime under **Privacy & consent** |
| 7 | **Respect for the user (user-centric)** | Self-service **access** (export), **correction** (email/phone via OTP-to-new-value), **withdraw** consent, and **delete** (immediate for enquiry-only); grievance route to us and to the Data Protection Board |

## DPDP alignment (data-principal rights)

| DPDP right | Where |
|---|---|
| Consent — free, specific, informed, itemized, withdrawable (§6) | `/client/me/consent` + catalog; AI training is a **separate declinable opt-in** (purpose limitation) |
| Access / portability (§11) | `/client/me/export` |
| Correction (§12) | `/client/me/change-contact` (+ verify) |
| Erasure (§12) | `/client/me/erasure-request` — immediate for enquiry-only (item 10), queued for project clients |
| Retention / storage limitation (§8(7)) | retention engine: 6-month enquiry, 10-year project; advance notice |
| Grievance / Board | notice text + `INCIDENT_RESPONSE.md` breach path |

## Data-minimization & purpose-limitation in practice

- **Collect less:** each purpose gathers only the fields it needs; export/erasure
  operate on an enumerated set (no hidden data).
- **Separate purposes:** distinct consents per purpose; training on personal data
  is never bundled into "accept all".
- **Keep less, shorter:** enquiry data expires at 6 months; PII is de-identified
  on erasure while statutory records are retained.
- **Show clearly:** versioned, plain-English notice; every consent choice is
  logged and reversible in-app.

## Applying PbD to new features (checklist)

1. What personal data does this need — and can it do less?
2. What is the **purpose**, and does it need its **own** consent?
3. What is the **default** — is it the privacy-protective one (off)?
4. How does the user **see, change, export and delete** this data?
5. What is the **retention** window and disposal method?
6. Which **security** controls protect it in transit, at rest, in logs?
7. Is the choice and the access **auditable**?

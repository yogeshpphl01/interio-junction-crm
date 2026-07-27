# DPDPA Compliance Blueprint — Interio Junction

**Scope:** the four applications — Customer Mobile, Customer Web, Staff Mobile, Staff Web — on the shared FastAPI + PostgreSQL backend.
**Basis:** India's **Digital Personal Data Protection Act, 2023 (DPDP Act)** and the **Digital Personal Data Protection Rules, 2025 (DPDP Rules)**.
**Status:** design + implementation blueprint. Version 1.0 · 26 July 2026.

> **Not legal advice.** This is an engineering compliance design derived from the DPDP Act/Rules. Have the consent text, retention schedule and grievance process reviewed by a qualified Indian privacy lawyer before go-live. Where the Rules leave a choice, we pick the privacy-protective option.

---

## 1. Who we are under the law

- **We are a _Data Fiduciary_** — we decide the purpose and means of processing customers' personal data.
- **We are (almost certainly) _not_ a Significant Data Fiduciary (SDF)** given our small volume, so the SDF-only duties (mandatory DPO, independent audit, DPIA) don't strictly apply. We will still appoint a **named Grievance/Contact person** and publish their details (required of every Data Fiduciary).
- **Data Principals** = our customers (leads and project clients). Staff are also data principals for their HR/login data.

## 2. DPDP in brief (what the law requires)

| Area | Requirement (DPDP Act 2023 + Rules 2025) |
|---|---|
| **Lawful basis** | Consent, or a listed "legitimate use". We rely on **consent** for customers; on **contract/legitimate use** for delivering a booked project. |
| **Consent** | Free, specific, informed, unconditional, unambiguous, by **clear affirmative action**; **itemized per purpose**; **withdrawal as easy as giving it**; withdrawal doesn't undo past lawful processing. |
| **Notice** (Rule 3) | Itemized list of data categories; each purpose + the service that relies on it; how to **withdraw**, **exercise rights**, **reach the grievance officer**, and **complain to the Data Protection Board (DPB)**. |
| **Rights** | Access/summary (s.11); correction, completion, updating, **erasure** (s.12); grievance redressal (s.13); **nominate** (s.14). |
| **Response times** | Rights requests: act within a published period (we adopt **30 days**). Grievances: **≤90 days**. |
| **Retention / storage limitation** | Erase when the purpose is served, consent is withdrawn, or the retention window lapses — with **advance notice** before erasure. |
| **Breach** | Notify the DPB **and** affected principals; a detailed report to the DPB **within 72 hours**. |
| **Children (<18)** | **Verifiable parental consent**; no tracking, profiling or targeted ads to children. |
| **Security (Rule 6)** | "Reasonable safeguards": **encryption** (AES-256 for consent/withdrawal logs), masking, access control, TLS in transit, **1-year** security logs, backups, monitoring. |
| **Penalties** | Up to **₹250 crore** for a failure to take reasonable security safeguards. |
| **Timeline** | Rules notified in 2025; most Data-Fiduciary obligations take effect ~**18 months** after notification (staged), so there is a runway — but we build now. |

## 3. Data inventory & purposes

| Data | Whom | Why (purpose) | Basis |
|---|---|---|---|
| Name, phone, email, city/address | Lead / customer | Respond to enquiry; deliver the interior project; support & warranty | Consent → then contract |
| Requirements, BHK, budget, site photos, designs, measurements | Customer | Design & build the project | Contract / consent |
| Payments, milestones | Customer | Billing, warranty, statutory records | Legal obligation / contract |
| Chat messages, documents | Customer | Project delivery & support | Contract / consent |
| **Derived/aggregated analytics; AI training data** | Customer (opt-in) | Improve service; AI features | **Separate opt-in consent** (§4) |
| Staff name, email, phone, role, login, MFA | Staff | Run the CRM; access control | Employment / legitimate use |

**PII flagged for encryption at rest:** phone, email (already implemented — AES-256-GCM + blind index). Extending to address on the roadmap.

## 4. Consent design

We split consent into **necessary** (needed to give the service) and **optional** (separately declinable). This is the crux of DPDP compliance and of your item 8.

| Purpose | Type | Notes |
|---|---|---|
| **Provide the enquiry response & interior project** (contact, design, build, support) | **Necessary** | Without this we can't serve you. Basis moves to *contract* once a project starts. |
| **Warranty & legal recordkeeping** (10 years) | **Necessary for project clients** | Legal/contractual — see retention (§5). |
| **AI model training & AI features** | **Optional opt-in** ✅ separate toggle | **Declinable** without losing the service. Trained on **de-identified/aggregated** data wherever feasible. Withdrawable. |
| **Analytics & service improvement** | **Optional opt-in** | Prefer anonymized/aggregated analytics (outside "personal data"). |
| **Marketing / promotions** | **Optional opt-in** | Off by default; unsubscribe = withdraw. |

**Why AI can't be bundled:** DPDP consent must be *free* and *unconditional*. Making the project conditional on agreeing to AI training would make the consent invalid. So AI/analytics/marketing are **separate opt-ins**, each recorded, versioned, timestamped, and independently withdrawable — and the customer keeps full service either way.

**Consent is recorded** with: principal id, purpose key, notice version, granted/withdrawn, timestamp, IP/app, and is stored in an **encrypted, tamper-evident** consent ledger (rides the existing hash-chained audit log; consent rows encrypted).

## 5. Retention schedule

| Data class | Retention | Then | Notice before erasure |
|---|---|---|---|
| **Enquiry-only leads** (never started a project) | **6 months** from last engagement | **Auto-erase / anonymize** | Notify **7 days** before erasure; lead can re-engage to preserve |
| **Project clients** | **10 years** from project completion | Review → erase/anonymize | Warranty & legal basis; explained in notice |
| **Security / access logs** | **1 year** | Erase | — |
| **Consent & withdrawal logs** | Life of relationship + statutory | Retain (proof of consent) | — |
| **AI-training datasets** | Only while opt-in stands; prefer de-identified | Erase/exclude on withdrawal | — |

A scheduled **retention job** runs daily: flags enquiry-only leads older than 6 months (minus any active engagement), sends the advance notice, then anonymizes/erases. Project clients are held 10 years for warranty/legal, then reviewed.

## 6. Data-principal rights — how we implement them

| Right | In-app implementation | Timeline |
|---|---|---|
| **Access / summary** (s.11) | "Your data" screen + **downloadable export** of what we hold and why | ≤30 days (instant in-app) |
| **Correction / completion / updating** (s.12) | Edit profile; **change email & phone** (item 9) with **OTP verification** of the new value | Immediate |
| **Erasure** (s.12) | **Enquiry-only leads:** self-service "Delete my data" (item 10). **Project clients:** request → staff review (retained for warranty/legal; erased when that lapses) | ≤30 days |
| **Grievance** (s.13) | In-app "Raise a privacy concern" → named Grievance Officer; DPB escalation info shown | ≤90 days |
| **Nominate** (s.14) | Nominee field to exercise rights on death/incapacity | On request |
| **Withdraw consent** | Toggle any optional consent off; as easy as granting | Immediate |

## 7. Security-by-design, Privacy-by-design, PII & ISMS

- **Security by Design (item 5):** the dual-BFF boundary, RBAC, least-privilege DB, encryption, signed URLs, MFA/passkeys, step-up, audit log, CI security gates — all built in from the start, not bolted on. Principle-by-principle mapping in **[`SECURITY_BY_DESIGN.md`](SECURITY_BY_DESIGN.md)**; see also `THREAT_MODEL.md`, `SECURITY_CI.md`.
- **Privacy by Design (item 7):** data minimization, purpose limitation (separate consents), default-off optional purposes, encryption of PII, short retention for enquiries, easy withdrawal, transparency via the notice. The 7 foundational principles mapped in **[`PRIVACY_BY_DESIGN.md`](PRIVACY_BY_DESIGN.md)**.
- **PII Security (item 1):** AES-256-GCM field encryption + blind index for phone/email; access-scoped; PII never in logs. Full inventory, classification and disposal in **[`PII_HANDLING.md`](PII_HANDLING.md)**.
- **Role-Based Access (item 6):** permission catalog + roles (sales, designer, accounts, supervisor, admin, CEO, system_admin); four-eyes on money; least privilege — see `permissions.py`.
- **ISMS (item 4):** lightweight ISO-27001-aligned management system — policies, asset & risk register, access control, incident response (`INCIDENT_RESPONSE.md`), backup/DR (`BACKUP_DR.md`), data retention (`DATA_RETENTION.md`), and a review cadence. Documented in **[`ISMS.md`](ISMS.md)**.
- **Information Security (item 3):** the organisation-level policy and control domains are in **[`INFORMATION_SECURITY_POLICY.md`](INFORMATION_SECURITY_POLICY.md)** (with `Interio_Junction_Security_Overview.pdf`).

## 8. Breach response (72-hour rule)

On a suspected breach: contain → assess → **notify the DPB without delay and a full report within 72 hours** (nature, extent, timing, impact, remediation, root cause) → notify affected principals (what happened, likely impact, steps taken, what they can do, contact). Runbook: [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md).

## 9. Children's data

Our service targets adults (homeowners). We will (a) state the service is not directed at under-18s, (b) add an **age affirmation** at signup, and (c) not knowingly process children's data or profile/target minors. If a guardian relationship ever applies, verifiable parental consent (Rule 10) would be required.

## 10. The 11 requested items → design & status

| # | Requested | Design | Status |
|---|---|---|---|
| 1 | PII Security | AES-256-GCM + blind index (phone/email); inventory + disposal — [`PII_HANDLING.md`](PII_HANDLING.md) | ✅ Built + documented |
| 2 | DPDPA across 4 apps | Consent + rights UI in all four apps + backend | ✅ Built |
| 3 | Information Security | Policy + control domains — [`INFORMATION_SECURITY_POLICY.md`](INFORMATION_SECURITY_POLICY.md) | ✅ Documented |
| 4 | ISMS | ISO-27001-aligned pack — [`ISMS.md`](ISMS.md) | ✅ Documented |
| 5 | Security by Design | Principle→control map — [`SECURITY_BY_DESIGN.md`](SECURITY_BY_DESIGN.md) | ✅ Built + documented |
| 6 | Role-Based Access | `permissions.py` roles + four-eyes | ✅ Built |
| 7 | Privacy by Design | 7 principles mapped — [`PRIVACY_BY_DESIGN.md`](PRIVACY_BY_DESIGN.md) | ✅ Built + documented |
| 8 | Consent management + custom consent + retention (6mo/10yr) + AI/analytics | Catalog (AI = separate opt-in) + retention engine (`retention.py`) | ✅ Built |
| 9 | Email & phone change | Self-service correction with OTP-to-new-value | ✅ Built (web + mobile) |
| 10 | Delete data (enquiry-only) | Immediate self-service erasure; project clients queued | ✅ Built |
| 11 | 3 failed → email+phone OTP reset | Change-password lockout → dual-channel OTP reset | ✅ Built (backend + web + mobile) |

---

## 11. Custom consent notice — Interio Junction (modular interiors)

> Plain-language notice shown at signup/first login and in "Privacy & consent". Itemized per Rule 3. **Bracketed** items to confirm before go-live.

**How Interio Junction uses your information**

When you enquire with us or start a project, we collect and use your personal data as set out below. Please review and choose your options. You can change these anytime under **Privacy & consent**.

**What we collect:** your name, phone number, email, city/address; your requirements, home type and budget; site photos, measurements, designs, documents, chat messages; and payment/milestone details for projects.

**Why we use it**
- **To respond to your enquiry and deliver your interior project** — design, manufacture, installation, support and warranty. *(Required to serve you.)*
- **To keep legal and warranty records** — if you do a project with us, we keep your project records for **10 years** to honour our **10-year warranty** and meet legal/contractual obligations. *(Required for project clients.)*
- ☐ **To improve our services and build AI features** — we may use your data (**de-identified where possible**) to build and train AI models and provide AI-assisted features. *(Optional — you can decline and still get full service.)*
- ☐ **For analytics** to improve our products and experience. *(Optional.)*
- ☐ **To send you offers and updates** by email/SMS/WhatsApp. *(Optional.)*

**How long we keep it:** if you only enquire and don't start a project, we keep your data for **6 months**, then delete it (we'll remind you before). If you do a project, we keep it for **10 years** for warranty and legal reasons.

**Your rights:** you can **access** a copy of your data, **correct** it (including changing your email or phone), **withdraw** any optional consent, and — if you only enquired and didn't start a project — **delete** your data, anytime in the app. You can also **raise a privacy concern**.

**Contact / Grievance Officer:** [Name], [email], [phone]. If unresolved, you may complain to the **Data Protection Board of India**.

**Confirmation:** ☑ I confirm I am 18 or older and I have read this notice. *(Optional toggles above are off unless you turn them on.)*

---

### Sources
- [EY — DPDP Act 2023 & DPDP Rules 2025 compliance guide](https://www.ey.com/en_in/insights/cybersecurity/decoding-the-digital-personal-data-protection-act-2023)
- [PRS India — Digital Personal Data Protection Bill, 2023](https://prsindia.org/billtrack/digital-personal-data-protection-bill-2023)
- [DPDP Rules 2025 — Rule 3 (Notice) & Rule 14 (Rights)](https://www.dpdpa.com/dpdparules/rule3.html)
- [Seclore — DPDP Rules 2025 compliance guide](https://www.seclore.com/fundamentals/dpdp-rules-2025-compliance-guide/)
- [Scrut — DPDP Rules 2025 implementation checklist](https://www.scrut.io/post/dpdp-rules)
- [MediaNama — DPDP Rules 2025 breach reporting timeline (72h)](https://www.medianama.com/2025/11/223-data-breach-reporting-timeline-of-dpdp-rules-2025-explained/)
- [Khurana & Khurana — AI training data under India's DPDP regime](https://www.khuranaandkhurana.com/ai-training-data-under-india-s-dpdp-regime-compliance-challenges-and-strategies)
- [DPDPA.com — AI/ML under DPDPA compliance guide](https://www.dpdpa.com/blogs/ai_machine_learning_dpdpa_compliance_guide.html)

# Incident response & data-breach runbook

Scope: Interio Junction CRM + the Client/Company mobile apps. Aligns with the
**India DPDP Act 2023 §8(6)** (breach notification), NIST CSF **RESPOND/RECOVER**,
ISO/IEC **27035**, and SANS incident handling (PICERL).

> **Owner:** the person acting as Data Protection Officer (DPO). Until formally
> appointed, the **CEO** holds this role. Keep this runbook printable and
> reachable **without** access to the production systems.

## 0. Roles (fill in real names/numbers before go-live)

| Role | Who | Contact |
|---|---|---|
| Incident Lead / DPO | CEO | … |
| Backend / infra | … | … |
| Comms (customers, DPB) | … | … |
| Legal | … | … |

## 1. Detect & report

Anyone who suspects an incident raises it **immediately** to the Incident Lead
(no blame for false alarms). Triggers include: unexpected data access in the
audit log, a leaked credential/secret (gitleaks alert), abnormal login/OTP
spikes, a lost/stolen device with app access, a third-party (FCM/storage/gateway)
breach notice, or a ransom/extortion message.

Start an **incident log** (timestamped, append-only) from this moment.

## 2. Contain (first hour)

- Revoke sessions: bump `token_version` for the affected user(s)/customer(s)
  (logout / deactivate / `POST /api/customers/{id}/erase` all do this), or
  rotate `JWT_SECRET` to invalidate **every** session at once.
- Rotate any exposed secret (DB creds, `JWT_SECRET`, FCM key, gateway keys) —
  see `SECRETS.md`.
- Disable a compromised account (`/users/{id}/deactivate`) or lock the app
  (`APP_CHECK_ENABLED=1`, tighten rate limits).
- Preserve evidence: snapshot logs, the audit table, and DB state **before**
  remediating.

## 3. Assess (what, whose, how much)

- What data classes are involved? (see `DATA_RETENTION.md` classification.)
- Whose personal data (how many data principals)? Use the audit log
  (`document.downloaded`, `privacy.data_exported`, auth events) to scope access.
- Is it still ongoing? Root cause?
- Grade severity: **P1** (PII of many principals / financial / ongoing) →
  **P3** (contained, no PII).

## 4. Notify (DPDP §8(6))

For a personal-data breach, notify **without undue delay**:

1. **The Data Protection Board of India** — nature, categories & approximate
   number of data principals, likely consequences, and the measures taken.
2. **Each affected data principal** — in clear language: what happened, what
   data, what they should do (e.g. re-login, watch for phishing), and our
   contact for questions.

Keep notification templates ready (see appendix). Log every notification sent.
Do not delay notification to finish the investigation — send what is known and
follow up.

## 5. Eradicate & recover

- Patch the root cause; verify the attacker path is closed.
- Restore from known-good backups if integrity is in doubt (see backup/DR plan).
- Force credential resets for affected accounts; keep pinning/App Check on.
- Monitor closely for recurrence for a defined watch period.

## 6. Post-incident review (within 2 weeks)

- Blameless timeline, root cause, what detected it, what slowed us down.
- Concrete fixes with owners + dates; fold new detections into monitoring.
- Update this runbook and the threat model.

## Appendix — data-principal notice (template)

> Subject: Important security notice about your Interio Junction account
>
> We are writing to let you know about a security incident that may have
> affected your personal data (<what data>). It happened on <date> and was
> contained on <date>. We have <actions taken>. We recommend you <action>.
> If you have questions, contact us at <contact>. We have also reported this to
> the Data Protection Board as required by law.

## Appendix — regulator notice (checklist)

- [ ] Nature of the breach
- [ ] Categories & approximate number of data principals affected
- [ ] Likely consequences
- [ ] Measures taken / proposed
- [ ] DPO contact

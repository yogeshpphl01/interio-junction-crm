# Backup, disaster recovery & monitoring

Operational resilience for the CRM + mobile backend. Aligns with NIST **CP**
(Contingency Planning) / **CP-9 backups**, **CP-10 recovery**, **AU/SI**
monitoring; ISO **A.8.13/A.8.14/A.5.29/A.5.30**; CIS **11**. Most of this needs
the production cloud environment to implement — this is the plan + runbook to set
it up and the values to fill in.

## 1. Targets (set concrete SLAs before go-live)

| Metric | Suggested target | Notes |
|---|---|---|
| **RPO** (max data loss) | ≤ 5 min | Postgres point-in-time recovery (WAL) |
| **RTO** (max downtime) | ≤ 4 h | restore + redeploy from IaC |
| Backup retention | 30 days PITR + monthly archival ≥ 1 yr | tax/DPDP retention (see `DATA_RETENTION.md`) |
| Restore drill cadence | quarterly | a backup you haven't restored is not a backup |

## 2. What to back up

| Data | Mechanism | Frequency |
|---|---|---|
| **PostgreSQL** | managed automated backups + **PITR/WAL archiving**; nightly logical `pg_dump` to a separate bucket | continuous WAL + nightly dump |
| **Object storage** (documents) | bucket **versioning** + cross-region replication; lifecycle to archive | continuous |
| **Secrets** (JWT, DB, gateway, FCM) | Secret Manager versioning; export an encrypted break-glass copy held offline | on change |
| **Config / IaC** | in git (this repo) + infra repo | per commit |
| **Audit log** | included in the DB backup; consider export to append-only storage | continuous |

Encrypt backups at rest; restrict who can read/delete them (a separate,
least-privilege backup role — an attacker who breaches the app must not be able
to delete backups). Keep at least one copy **immutable / offline** (ransomware).

## 3. Restore procedure (DB)

1. Freeze writes / put the app in maintenance.
2. Provision a fresh Postgres instance.
3. Restore the latest base backup, then replay WAL to the target timestamp
   (just before the incident) for PITR.
4. Point the app at the restored DB via `DATABASE_URL` (the `ij_app` role).
5. Run `python migrate.py` only if the schema is behind (`ij_migrate` role).
6. Smoke-test: login, an OTP flow, a payment read, a document signed-URL.
7. Rotate any secret that may have been exposed in the incident (`SECRETS.md`).
8. Lift maintenance; watch error/latency dashboards.

Document object-storage and secret restores similarly.

## 4. DR scenarios

| Scenario | Response |
|---|---|
| Accidental data deletion / bad migration | PITR to just before the change (§3) |
| Region outage | redeploy backend (stateless, Cloud Run) in a second region; restore DB from cross-region backup; repoint DNS |
| Ransomware / integrity compromise | restore from the **immutable/offline** copy; rotate all secrets; follow `INCIDENT_RESPONSE.md` |
| Secret leak | rotate (JWT bump invalidates sessions); redeploy |

## 5. Monitoring & alerting (SI / AU-6)

Wire these once on the production platform (e.g. Cloud Monitoring + Logging):

**Availability / performance**
- Uptime check on `/api` health; alert on failure.
- p95 latency + 5xx rate per route; alert on spikes.
- DB connections/CPU/replication lag; disk space.

**Security signals (from the audit log + app logs)**
- Burst of `auth.login_failed` / lockouts (credential stuffing).
- OTP request/`client.otp_failed` spikes (enumeration / SMS-bombing).
- `auth.mfa_failed` bursts; MFA disabled.
- Privileged events — `user.deleted`, role changes, `privacy.erased`,
  `payment.refunded`, `payment.amount_mismatch`, `payment.webhook_rejected` —
  alert a human in real time.
- `auth.break_glass` (CEO/super-account login) — page on-call in real time.
- `security.bulk_read` — a single staff list read returned ≥
  `BULK_READ_ALERT_THRESHOLD` (default 100) PII-bearing records; a mass-read /
  exfiltration signal. `metadata` carries `{resource, count, threshold}`.
- `token_version`/revocation surges; step-up failures.
- gitleaks / pip-audit / bandit CI failures.

**Delivery**
- Route P1 alerts to an on-call channel + phone; others to a dashboard.
- Every alert links to the relevant runbook (this file / `INCIDENT_RESPONSE.md`).

## 6. Readiness checklist

- [ ] Managed DB backups + PITR enabled; retention set
- [ ] Nightly `pg_dump` to a separate, least-privilege bucket
- [ ] Object-storage versioning + replication
- [ ] Secret Manager versioning + offline break-glass copy
- [ ] Backups encrypted; delete-protected; one immutable/offline copy
- [ ] Quarterly restore drill scheduled + a completed test restore on record
- [ ] Uptime + latency + 5xx + DB dashboards and alerts
- [ ] Security-event alerts wired from the audit log
- [ ] RPO/RTO agreed and documented

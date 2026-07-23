# Threat model — Interio Junction (Client App, Company App, shared backend)

STRIDE threat model for the two-app ecosystem on the shared FastAPI + PostgreSQL
backend. Maps each threat to the control that addresses it (✅ built & verified,
🟡 partial/config, ❌ open) so residual risk is explicit. Pairs with
`MOBILE_SECURITY_STANDARDS.md` (control catalog), `INCIDENT_RESPONSE.md`,
`DATA_RETENTION.md`, `BACKUP_DR.md`.

## 1. Assets

| Asset | Sensitivity |
|---|---|
| Customer PII (name, phone, email) | high (DPDP personal data) |
| Staff credentials + MFA secrets/backup codes | critical |
| Payments (booking/milestones, gateway refs) | high (financial) |
| Estimates / contract values | high (commercial) |
| Documents (renders, CAD, quotations, site photos) | medium–high |
| Audit log | high (integrity — accountability) |
| JWT signing secret, DB creds, gateway/webhook secrets, FCM key | critical |

## 2. Trust boundaries

- **Client App ↔ backend** — customers, phone-OTP identity (`customer_access`
  tokens). Untrusted device.
- **Company App ↔ backend** — staff, password + MFA (`access` tokens, AAL). RBAC.
- **Dual-BFF boundary** — the two token families are mutually rejected
  (`get_current_user` vs `get_current_customer`): a customer token can never
  reach a staff/RBAC endpoint and vice-versa. This is the primary isolation line.
- **Backend ↔ Postgres** — least-privilege DB roles (`ij_app` DML-only at
  runtime; `ij_migrate` for DDL). 
- **Backend ↔ processors** — FCM, object storage, Razorpay (webhook HMAC).
- **Public webhook** — Razorpay → backend (signature-verified, idempotent).

## 3. STRIDE

### Spoofing (identity)
| Threat | Control |
|---|---|
| Guessing/replaying staff passwords | ✅ progressive lockout (P0-3); ✅ **MFA/AAL2 TOTP** for enrolled staff (P1-6); ✅ instant revocation (P1-7) |
| Stolen/replayed Bearer token after logout | ✅ `token_version` — logout/deactivate/credential-change kill it at once (P1-7) |
| Customer OTP interception / SIM-swap | 🟡 OTP is a single possession factor; rate-limited + daily-capped (P0-3/A4); ⬜ add biometric step-up for high-risk customer actions (A9) |
| Bot/script hitting OTP/login at scale | 🟡 lockout + caps; ✅ **App Check** attestation gate ready (P1-8, flip `APP_CHECK_ENABLED`) |
| Forged payment-gateway callback | ✅ Razorpay **HMAC signature** verification, unsigned rejected (P1-13) |
| Customer token used on a staff endpoint | ✅ dual-BFF token-type rejection |

### Tampering (integrity)
| Threat | Control |
|---|---|
| Client-supplied payment amount | ✅ amount is server-derived from the accepted estimate; gateway amount matched to the order (P1-13) |
| Repackaged/modified app | 🟡 App Check + Play Integrity/App Attest (P1-8, config); 🟡 obfuscation/tamper checks (P1-12, config) |
| MitM on API traffic | ✅ HTTPS enforced (P0-2); 🟡 cert pinning hook + Android `<pin-set>` (P1-8, supply pins) |
| Malicious file upload (stored XSS / exe) | ✅ magic-byte allow-list + safe content-type + `nosniff` (P1-10) |
| Tampering with the audit log | 🟡 append-only by convention; DB write-role limited (P0-4); ⬜ consider WORM/hash-chaining |
| SQL injection | ✅ parameterized throughout (schema-driven shim); ✅ bandit in CI (P1-14) |

### Repudiation (accountability)
| Threat | Control |
|---|---|
| "I didn't approve/confirm/refund that" | ✅ immutable audit on auth, payments, approvals, refunds, privacy actions; four-eyes records both parties (P1-9/P1-13) |
| Shared admin/CEO accounts blur accountability | 🟡 named-account policy documented (Part 4 SoD-4); ⬜ enforce |
| Silent privileged action | ✅ audited; ⬜ real-time alerting on privileged events (see BACKUP_DR §monitoring) |

### Information disclosure (confidentiality)
| Threat | Control |
|---|---|
| Secrets in code/logs/repo | ✅ env + fail-fast validation (P0-5); ✅ OTP/reset codes never logged in prod; ✅ gitleaks in CI |
| Leaking internal storage paths / documents | ✅ signed URLs, no `storage_path` exposed, per-project/customer authZ (P1-10) |
| PII over-exposure to staff by role | ✅ RBAC + lead/project visibility scoping; ✅ least-privilege re-map (P1-9) |
| Insider mass-read / bulk export of PII (compromised or rogue staff account) | ✅ **detective** `security.bulk_read` audit event when one list read returns ≥ `BULK_READ_ALERT_THRESHOLD` (default 100) records → real-time alert (J-domain, `BACKUP_DR §5`); tamper-evident via hash-chained audit log. ⬜ per-account daily read-volume quotas |
| Enumeration of customers via OTP endpoint | ✅ generic responses, no existence oracle (A4) |
| PII at rest readable if DB dumped | ✅ **AES-256-GCM field encryption + blind index** for customer phone/email (env-gated `PII_ENCRYPTION_KEY`, §5); TLS + least-priv DB. ⬜ prod KMS key + extend to leads/staff |
| Data-subject can't see/remove their data | ✅ DPDP export + erasure (P1-11) |

### Denial of service (availability)
| Threat | Control |
|---|---|
| Login/OTP flooding | 🟡 per-account lockout + per-phone caps (P0-3); ⬜ per-IP + global limits at the gateway/Cloud Armor (I1/I2) |
| Large-file upload abuse | ✅ 25 MB cap + validation (P1-10) |
| Webhook replay storm | ✅ idempotency ledger (P1-13) |
| Dependency/DoS CVEs (e.g. starlette) | 🟡 pip-audit surfaces them (P1-14); ⬜ upgrade fastapi/starlette |
| Data loss / outage | 🟡 backups/DR — see `BACKUP_DR.md` (needs prod infra) |

### Elevation of privilege
| Threat | Control |
|---|---|
| Sales banking their own deal (create+confirm) | ✅ record/confirm split; Sales can't confirm (P1-9) |
| Self-approval (maker=checker) | ✅ four-eyes on estimate/expense/payment/booking/refund — incl. admin/CEO (P1-9/P1-13) |
| Admin as money super-user | ✅ admin stripped of `payments.confirm`/`refund`/umbrella (split admin, P1-9) |
| Stale elevated session after demotion | ✅ role read fresh per request + `token_version` bump on role change (P1-7/P1-9) |
| Refund abuse | ✅ dedicated `payments.refund` (finance/CEO only) + four-eyes + step-up (P1-13) |
| Deactivated staff still acting | ✅ deactivation revokes tokens instantly (P1-7) |

## 4. Top residual risks (priority order)

1. **starlette CVEs** — upgrade fastapi/starlette (tracked, P1-14).
2. **App Check / pinning / mobile hardening are config-pending** — flip
   `APP_CHECK_ENABLED`, supply cert pins, wire FLAG_SECURE/manifest (P1-8/P1-12).
3. **Per-IP / global rate limiting** at the edge (Cloud Armor) — not just
   per-account (I1/I2).
4. ✅ **PII column-level encryption** for phone/email at rest — *implemented* (§5, C6); remaining: a prod **KMS** key + extending `encrypted:` to leads/staff PII.
5. **Real-time alerting + backups/DR** — needs prod infra (`BACKUP_DR.md`).
6. **Customer second factor** for high-risk actions (biometric step-up, A9).

## 5. PII column-level encryption (C6) — implemented

`phone` and `email` have **unique** constraints and are the login/lookup keys, so
naive encryption breaks lookups. The implemented scheme (`pii_crypto.py` + the
data-layer shim) is the **encrypted-column + blind-index** pattern:

- The stored value is **AES-256-GCM** encrypted (randomised — same plaintext →
  different ciphertext), so a raw DB dump reveals nothing.
- A companion **`<col>_bidx`** holds a deterministic **HMAC-SHA256** of the
  normalised value; the UNIQUE constraint and every equality/`$in`/`$ne` lookup
  are transparently rewritten onto it, so uniqueness and phone/email lookups keep
  working. Blind-index columns are never returned to callers.
- Enc + index subkeys are derived from a single **`PII_ENCRYPTION_KEY`** (base64
  32-byte master). It is **env-gated and backward compatible**: unset → plaintext
  as before; `decrypt()` passes through legacy plaintext, and `migrate_pii.py`
  backfills existing rows idempotently.

Verified: 30 checks with the flag on (round-trip, at-rest ciphertext, blind-index
lookup, UNIQUE enforcement, update re-encryption, migration, end-to-end OTP) and
40 with it off (unchanged). **Production TODO:** load `PII_ENCRYPTION_KEY` from a
**KMS / Secret Manager** (the loader in `pii_crypto._master_key` is the single
swap point), rotate keys with a versioned prefix, and extend the `encrypted:`
declaration to leads/staff PII.

Historical alternatives considered: Postgres `pgcrypto`, AES-SIV deterministic
encryption. This is a careful data-layer change (migration + every read/write path touching
phone/email) — design first, roll out behind a flag.

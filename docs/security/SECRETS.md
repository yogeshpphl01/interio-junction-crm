# Secrets & configuration management

NIST SC‑12 / CIS Control 4 & 16 / OWASP API8 / CWE‑798. **No secret is ever
committed.** The app reads them from the environment; production injects them
from a secrets manager.

## Required environment variables

| Var | Purpose | Prod requirement |
|---|---|---|
| `JWT_SECRET` | signs access/refresh JWTs | **≥ 32 chars, high‑entropy, unique per env**; app refuses to start otherwise |
| `DATABASE_URL` (or `PG_*`) | Postgres DSN | use the **`ij_app`** role (DML‑only) at runtime; `ij_migrate` only for `migrate.py` |
| `APP_ENV` | `production` toggles enforcement (HTTPS, secret strength, no OTP logging) | set to `production` |
| `RUN_MIGRATIONS` | `0` in prod so the app needs no DDL | `0` |
| `CORS_ORIGINS` | exact allowed web origins | pin (never `*` with credentials) |
| `ENFORCE_HTTPS` | reject cleartext (default on in prod) | leave on |
| `OTP_DEBUG_LOG` | **dev only** — log OTP codes | never set in prod (ignored anyway) |
| `STEP_UP_ENABLED` | require a fresh second factor on privileged actions (payment confirm, approvals, role change, delete) — P1‑9 | `1` once all staff have enrolled MFA (else those actions 403) |
| `APP_CHECK_ENABLED` | enforce Firebase App Check attestation on OTP/login — P1‑8 | `1` once every app build sends a valid token (fail‑closed) |
| `APP_CHECK_PROJECT_NUMBER` | Firebase project number; pins App Check aud/iss | set when `APP_CHECK_ENABLED=1` |
| `APP_CHECK_JWKS_URL` / `APP_CHECK_JWKS_JSON` | App Check public keys (default Google URL; JSON pins them inline) | optional |
| `RAZORPAY_WEBHOOK_SECRET` | HMAC secret to verify Razorpay webhooks — P1‑13 | set when the gateway is live (endpoint is inert/503 without it) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | gateway order creation (when enabled) | Secret Manager only |
| `PAYMENT_STEP_UP_THRESHOLD` | ₹ amount at/above which confirm+refund force a step‑up — P1‑13 | set once MFA is rolled out (0/unset = off) |
| `PII_ENCRYPTION_KEY` | base64 32‑byte master key for field‑level PII encryption (phone/email) — C6 | load from **KMS/Secret Manager**; run `migrate_pii.py` after enabling; unset = plaintext |
| `CLIENT_STEP_UP_ENABLED` | require a customer biometric step‑up on accept‑estimate/approve‑design — A9 | `1` once the app ships the biometric prompt (0/unset = off) |
| `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` / `WEBAUTHN_RP_NAME` | passkey relying‑party id + origin (A8) | set to your prod host (`app.…`, `https://app.…`); passkeys need HTTPS |
| `BULK_READ_ALERT_THRESHOLD` | record count at/above which a single staff list read emits a `security.bulk_read` alert (PII‑exfiltration signal) — J‑domain | default `100`; lower for tighter monitoring, higher for large datasets |
| `GOOGLE_APPLICATION_CREDENTIALS` / `FCM_*` | push service account | store as a mounted secret, not in the image |

`validate_security_config()` runs at startup and **fails fast** in production if
`JWT_SECRET` is missing/weak or the DB is unconfigured.

## Where secrets live

- **Production:** GCP **Secret Manager** (or Vault). Grant each service account
  read access only to the secrets it needs; mount/inject at runtime; enable
  access audit logging. Cloud SQL creds via the Cloud SQL connector / IAM auth.
- **Local dev:** an untracked `backend/.env` (already git‑ignored). Never share
  prod secrets with dev/CI.
- **CI:** GitHub Actions **encrypted secrets**; never echo them into logs.

## Rotation

Rotate on any suspected exposure and on a schedule: `JWT_SECRET` (supports
overlap once we move to `kid`/asymmetric — see MOBILE_SECURITY_STANDARDS E2/E4),
DB passwords, FCM service account, payment‑gateway keys. Rotating `JWT_SECRET`
invalidates existing tokens (acceptable; users re‑login).

## Preventing leaks

- `.gitignore` covers `.env`, native Firebase config, keystores.
- **gitleaks** runs in CI (`.github/workflows/secret-scan.yml`, config
  `.gitleaks.toml`) and fails the build on a finding.
- Enable **GitHub secret scanning + push protection** on the repo.
- Never paste secrets into code, comments, commit messages, or issues.

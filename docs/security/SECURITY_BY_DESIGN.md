# Security by design (item 5)

Security is built into the architecture and the SDLC, not added afterwards. This
records the principles and, for each, **how the Interio Junction codebase already
embodies it** — so a reviewer can trace principle → control → code.

Related: [`INFORMATION_SECURITY_POLICY.md`](INFORMATION_SECURITY_POLICY.md) ·
[`PRIVACY_BY_DESIGN.md`](PRIVACY_BY_DESIGN.md) ·
[`THREAT_MODEL.md`](THREAT_MODEL.md) · [`SECURITY_CI.md`](SECURITY_CI.md).

## Principles → implementation

| # | Principle | How we implement it |
|---|---|---|
| 1 | **Least privilege** | RBAC permission catalog (`permissions.py`); every privileged route uses `require_permission`; UI hides what the role can't do |
| 2 | **Separation of duties** | Four-eyes on finance (approver ≠ creator, `deny_self_action`); break-glass CEO account is alerted on every login |
| 3 | **Defense in depth** | TLS + HSTS, auth, RBAC, step-up, field encryption, audit — no single control is load-bearing |
| 4 | **Secure defaults** | Optional consents default off; step-up/attestation gates ship wired but opt-in; release builds refuse non-HTTPS bases |
| 5 | **Fail securely** | Auth failures deny; locked accounts are refused before password checks; generic errors avoid enumeration |
| 6 | **Complete mediation** | Every request re-derives identity + permissions server-side (`get_current_user`); no trust in client-supplied role |
| 7 | **Strong authentication** | Staff password + **TOTP MFA** + **passkeys/WebAuthn**; **step-up** re-auth on sensitive actions; customer phone-OTP + biometric step-up |
| 8 | **Isolation (dual-BFF)** | Customer and staff are separate token families that are **mutually rejected**; customer portal is bearer-only (no cookies) |
| 9 | **Tamper-evidence** | **Hash-chained audit log** (`audit.py`) with an on-demand `/audit/verify-chain` integrity check |
| 10 | **Data protection** | AES-256-GCM field encryption for PII (`pii_crypto.py`) with blind indexes; secrets never logged |
| 11 | **Brute-force & abuse resistance** | Per-account login lockout with backoff; **change-password lockout → email+phone OTP reset** (item 11); OTPs hashed, short-TTL, attempt-capped; **per-IP rate limiting on the auth/OTP endpoints** (`ratelimit.py`, API4) to stop spray/OTP-bombing across accounts |
| 12 | **Instant revocation** | `token_version` bump invalidates all of a principal's tokens (on password change, erasure, reset) |
| 13 | **Input validation** | Pydantic models validate/normalize every request body; parameterized DB access |
| 14 | **Mobile hardening** | App Check/attestation gate, secure token storage, screen-capture protection, TLS cert pinning ([`MOBILE_SECURITY_STANDARDS.md`](MOBILE_SECURITY_STANDARDS.md)) |
| 15 | **Secure SDLC** | Threat model, code review on a branch model, CI dependency + secret scanning ([`SECURITY_CI.md`](SECURITY_CI.md)) |

## In the development lifecycle

- **Design:** threat-model new surfaces (STRIDE) against `THREAT_MODEL.md`;
  choose the privacy-protective default.
- **Build:** reuse the shared gates (`require_permission`, `assert_step_up`,
  `pii_crypto`, audit) rather than re-inventing; validate all input.
- **Verify:** authz test suite (BOLA/BFLA/dual-BFF), feature tests, CI scans;
  no secrets/PII in logs.
- **Operate:** least-privilege access reviews, audit-chain verification, backup
  drills, incident readiness — governed by [`ISMS.md`](ISMS.md).

## Standards touchpoints

OWASP ASVS, OWASP MASVS (mobile), NIST 800-53 (AC/IA/AU/SC), NIST 800-63B
(authentication & step-up), ISO/IEC 27001 Annex A.

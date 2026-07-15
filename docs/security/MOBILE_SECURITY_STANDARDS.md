# Interio Junction — Mobile Security Standards, Controls & Recommendations

Security requirements for the **Client App** (customers), the **Company App**
(employees), and the shared **FastAPI/PostgreSQL backend**, mapped to **OWASP
(MASVS, Mobile Top 10, API Security Top 10, ASVS)**, **NIST (SP 800‑63B, SP
800‑53r5, SP 800‑163/124, CSF 2.0)**, **ISO/IEC (27001:2022, 27002, 27017/27018,
27701)** and **SANS (CIS Controls v8, CWE Top 25)** — plus India's **DPDP Act
2023** (the apps hold consumer PII).

This is an audit + action document, not a claim of certification. It states, per
control, what the system does **today** and what to **do next**.

## How to read

- ✅ **In place** — implemented and verified this build.
- 🟡 **Partial** — foundation exists; hardening or config still required.
- ❌ **To‑do** — recommended control not yet present.

Status reflects the code in this repo (`backend/`, `mobile/`). It is deliberately
honest — several important controls are ❌ and are called out so nothing is missed.

## System recap (attack surface)

| Layer | What | Sensitive assets |
|---|---|---|
| Client App (Flutter) | Customer identity, phone‑OTP login | customer PII (name/phone/email/address), estimate/pricing, payment status, JWT |
| Company App (Flutter) | Employee identity, RBAC | all customer data, production/QR, financials, JWT, RBAC scope |
| Backend (FastAPI) | Dual‑BFF (`/api/client/*` vs company surface), RBAC, OTP, JWT | everything; DB credentials; JWT secret; audit log |
| Data/Infra | PostgreSQL, object storage, FCM, Infurnia, UPI/Razorpay | PII at rest, files, push tokens, payment refs |

Trust boundaries: **customer ↔ backend**, **employee ↔ backend**, **backend ↔
Postgres**, **backend ↔ external (FCM, Infurnia, payment gateway, storage)**, and
the **dual‑BFF wall** between the two identity worlds.

---

# Part 1 — Consolidated control checklist (by domain)

Each row: the control, the standard(s) it satisfies, current status, and the
concrete recommendation for this system.

## A. Authentication & Session Management
*(OWASP MASVS‑AUTH, Mobile M3, API2; ASVS V2/V3; NIST 800‑63B; 800‑53 IA‑2/IA‑5/AC‑12; ISO A.5.17/A.8.5; CIS 6; CWE‑287/384/613/307)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| A1 | Passwords hashed with a slow, salted KDF | ASVS V2.4; 800‑63B; A.8.24; CWE‑916 | ✅ bcrypt (`auth_utils.hash_password`) | Move work factor to ≥12; migrate to Argon2id when convenient. |
| A2 | Credentials never logged / in source | 800‑53 IA‑5; A.8.15; CWE‑532 | ✅ OTP/reset codes now gated behind `OTP_DEBUG_LOG` (dev‑only) + force‑off when `APP_ENV=prod`; prod logs a redacted line, never the code | Keep scrubbing tokens/PII from all logs; extend the gate to any future secret log. |
| A3 | Server‑side brute‑force / lockout on login | 800‑63B §5.2.2; ASVS V2.2; CWE‑307 | 🟡 OTP has 5‑try lockout + resend cooldown; **password login has none** | Add per‑account + per‑IP throttling and progressive backoff/lockout on `/auth/login`. |
| A4 | Rate‑limit OTP request (anti‑enumeration + SMS‑bombing) | 800‑63B; API4 | 🟡 60s per‑phone cooldown; generic response (no enumeration) | Add per‑IP + global request caps; CAPTCHA/App‑Check on repeated requests. |
| A5 | Short‑lived access token + refresh | ASVS V3.3; 800‑63B §7 | ✅ access 8h (staff)/24h (customer), refresh 7d/60d, typed | Shorten staff access to ≤1h; see A6/A7. |
| A6 | Refresh‑token rotation + reuse detection | ASVS V3.3; 800‑63B §7.2 | ❌ refresh tokens are static, reusable | Rotate on every refresh; detect reuse → revoke the family. |
| A7 | Token revocation / real logout | ASVS V3.3; A.8.5; CWE‑613 | ❌ logout only clears the client; tokens stay valid to expiry | Add a server‑side revocation list (jti/`kid`) or short TTL + rotation; revoke on logout/role‑change/deactivation. |
| A8 | MFA for employees | **800‑63B AAL2**; API2; A.8.5; CIS 6.3/6.4 | ❌ employees are **password‑only** | **Mandatory MFA (TOTP) for all staff; phishing‑resistant (FIDO2/passkey) for admin/CEO.** See Part 3. |
| A9 | Second factor / step‑up for customers on high‑risk actions | 800‑63B; M3 | 🟡 phone‑OTP is a single possession factor | Add device biometric/PIN as a second factor for accept‑estimate & payments (step‑up). See Part 3. |
| A10 | Idle + absolute session timeout | ASVS V3.3; 800‑53 AC‑11/AC‑12 | 🟡 token TTL only | Enforce inactivity re‑auth in‑app; require re‑login on token expiry (no silent infinite refresh for staff). |
| A11 | Bind session to device; detect impossible travel | 800‑63B; API2 | ❌ | Record device id on FCM/token issue; flag concurrent/geo‑anomalous sessions for staff. |
| A12 | Password policy: ≥8 chars, screen against breach lists, **no forced rotation/composition** | **800‑63B §5.1.1** | 🟡 min‑8 only | Add breached‑password check (k‑anonymity/HIBP); keep no‑rotation/no‑composition per NIST; allow long passphrases + paste. |
| A13 | Secure credential recovery | ASVS V2.5; 800‑63B §6 | ✅ email‑OTP reset (hashed, TTL, lockout) | Recovery must itself pass MFA for staff; rate‑limit; notify on reset. |
| A14 | Neutral auth errors (no user enumeration) | ASVS V2.2; CWE‑203 | ✅ "Invalid credentials"/generic OTP responses | Keep; apply same to registration/reset timing. |

## B. Authorization & Access Control (RBAC / multi‑tenant)
*(OWASP API1 BOLA, API3 BOPLA, API5 BFLA; MASVS‑AUTH; ASVS V4; NIST 800‑53 AC‑2/3/6; ISO A.5.15/A.5.18/A.8.2/A.8.3; CIS 5/6; CWE‑639/862/863/285)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| B1 | Server‑side authorization on every endpoint | API5 BFLA; ASVS V4.1; AC‑3 | ✅ `require_permission` gates writes; reads scoped | Add automated tests that every route asserts a gate (deny‑by‑default). |
| B2 | Object‑level authZ (no IDOR/BOLA) | **API1 BOLA**; CWE‑639 | ✅ customer data scoped by `customer_id`; 404 (not 403) hides others' objects | Extend the same ownership check to every new object type; add BOLA tests to CI. |
| B3 | Dual‑BFF identity separation | API2/API5; AC‑6 | ✅ `customer_access` vs `access` token types mutually rejected | Keep tokens in separate namespaces; never share a signing key purpose across audiences (add `aud` claim). |
| B4 | Least privilege in roles | **AC‑6**; A.8.2; CIS 6.8 | 🟡 8 roles/28 perms; `admin`≈ALL, `ceo`=ALL | Split super‑roles; see Part 2 (Segregation of Privileges). |
| B5 | Mass‑assignment / property‑level authZ | **API3 BOPLA**; CWE‑915 | 🟡 Pydantic models constrain input; some PATCH allow‑lists | Explicit allow‑lists on all write models; never bind whole request to ORM/doc. |
| B6 | Server‑authoritative business values | API6; CWE‑840 | ✅ estimate totals & booking amount computed server‑side | Keep; never trust client‑sent money/stage/role. |
| B7 | Protect sensitive business flows (abuse) | **API6** | 🟡 idempotency on booking/scans | Add anti‑automation on bulk endpoints (campaign import, distribute, scan). |
| B8 | Deactivation/role change takes effect immediately | AC‑2; A.5.18 | 🟡 `is_active` checked at auth; tokens live until expiry | Tie to A7 revocation so deactivated staff lose access at once. |

## C. Data Storage (mobile) & Data‑at‑Rest (backend)
*(OWASP MASVS‑STORAGE, Mobile M9; ASVS V6; NIST 800‑53 SC‑28/MP; ISO A.8.10/A.8.11/A.8.12; 27018; CIS 3; CWE‑312/311/922)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| C1 | Tokens/secrets in Keystore/Keychain, not plain prefs | **MASVS‑STORAGE‑1**; M9 | ✅ `flutter_secure_storage` (Keystore/Keychain) | Set Android `EncryptedSharedPreferences`/StrongBox where available; iOS `first_unlock_this_device`. |
| C2 | No sensitive data in logs/cache/backups | MASVS‑STORAGE‑2; M9 | 🟡 | Set Android `allowBackup=false` + `fullBackupContent` excludes; disable auto‑backup of tokens; no PII in Flutter logs. |
| C3 | Screenshot/recents & screen‑capture protection on sensitive screens | MASVS‑PLATFORM; M9 | ❌ | `FLAG_SECURE` (Android) / hide on background (iOS) for login, payments, estimates, PII. |
| C4 | Keyboard cache / autofill / clipboard hygiene | MASVS‑STORAGE; M9 | ❌ | Disable suggestions on OTP/amount fields; clear clipboard for copied codes; `autocorrect:false`, `enableSuggestions:false`. |
| C5 | DB encryption at rest | SC‑28; A.8.11; 27018 | 🟡 depends on Cloud SQL config | Enable Cloud SQL CMEK; encrypt backups; document key ownership. |
| C6 | Field‑level encryption for high‑sensitivity PII | SC‑28; A.8.11; DPDP | ❌ | Consider app‑level encryption for phone/email/address or tokenization; at minimum column‑level for payment refs. |
| C7 | Object‑storage access is signed & least‑privilege | SC‑12; A.5.14; API1 | 🟡 storage disabled in this env; `storage_path` returned as ref | Serve documents via **short‑lived signed URLs**, authZ‑checked per customer/project; private bucket only. |
| C8 | Data classification & retention | A.5.12/A.5.34; DPDP §8(7) | ❌ | Classify PII vs internal; set retention + purge for OTPs, audit, leads, closed projects. |

## D. Network & Transport Security
*(OWASP MASVS‑NETWORK, Mobile M5; ASVS V9; NIST 800‑53 SC‑8/SC‑13/SC‑23; ISO A.8.20/A.8.21/A.8.24; CIS 3.10; CWE‑319/295/297)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| D1 | TLS 1.2+ everywhere, no cleartext | **MASVS‑NETWORK‑1**; M5; SC‑8; CWE‑319 | 🟡 HTTPS assumed; default base URL is `http://10.0.2.2` (emulator only) | Enforce HTTPS in prod builds; Android `network_security_config` `cleartextTrafficPermitted=false`; ATS on iOS. |
| D2 | Certificate / public‑key pinning | MASVS‑NETWORK‑2; CWE‑295 | ❌ | Pin the API cert/SPKI in both apps (Dio `badCertificateCallback` or `http` pinning); plan rotation/backup pins. |
| D3 | Reject invalid/expired certs (no bypass) | CWE‑295/297 | 🟡 default Dio validates | Never disable cert validation; the proxy‑bypass note in ops must not ship to prod. |
| D4 | HSTS + secure response headers | ASVS V14.4; A.8.20 | ❌ | Add HSTS, `X‑Content‑Type‑Options`, `Referrer‑Policy`, `Cache‑Control:no‑store` on auth responses at the gateway. |
| D5 | CORS locked down | ASVS V14.5; API8 | 🟡 `CORS_ORIGINS` configurable, defaults `*` (creds off) | Pin exact origins for any web; mobile uses no CORS — keep `*` off in prod. |
| D6 | Mutual TLS / signed webhooks for gateways | API10; SC‑8 | 🟡 Razorpay webhook signature in reference code | Verify Razorpay signature on the live path; allow‑list gateway IPs; validate Infurnia payloads. |

## E. Cryptography & Key Management
*(OWASP MASVS‑CRYPTO, Mobile M10; ASVS V6; NIST SP 800‑57, 800‑53 SC‑12/13/17; ISO A.8.24; CWE‑327/330/338)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| E1 | Strong, standard algorithms only | MASVS‑CRYPTO‑1; CWE‑327 | ✅ bcrypt, HMAC‑SHA256 (JWT) | Keep; no home‑grown crypto. |
| E2 | JWT signing: prefer asymmetric + key id | ASVS V3.5; SC‑12 | 🟡 **HS256 shared secret** | Move to **RS256/ES256** (private key signs, public verifies); add `kid` + `aud`; enables rotation & separation. |
| E3 | Secure secret storage / no secrets in code | **SC‑12**; A.8.24; CWE‑798 | 🟡 `JWT_SECRET`, DB creds from env | Use a secrets manager/KMS (GCP Secret Manager); never commit; rotate on exposure. |
| E4 | Key rotation policy | SP 800‑57; A.8.24 | ❌ | Define rotation for JWT keys, DB creds, gateway keys, FCM service account; support overlapping `kid`. |
| E5 | CSPRNG for codes/tokens | CWE‑330/338 | ✅ `secrets.randbelow` for OTP, `uuid4` ids | Keep; ensure OTP entropy adequate (consider 6‑digit). |

## F. Input Validation, Output Encoding & Injection
*(OWASP MASVS‑CODE, Mobile M4; API8; ASVS V5; NIST SI‑10; ISO A.8.28; CIS 16; CWE‑89/79/20/78/611/94)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| F1 | Parameterized DB queries (no SQLi) | **CWE‑89**; SI‑10 | ✅ asyncpg parameter binding throughout (no string‑built SQL) | Keep; ban f‑string SQL in review; add a lint/CI check. |
| F2 | Server‑side schema validation of all input | ASVS V5.1; M4; API8 | ✅ Pydantic models on every endpoint | Add bounds (amount>0 exists), length caps, enum checks on free‑text (kind/type already enum‑checked). |
| F3 | Output encoding / no injection into logs, PDFs, deep links | CWE‑79/117 | 🟡 | Encode user text in any generated PDF/HTML; sanitize before logging (also A2). |
| F4 | File‑upload validation (docs, screenshots) | ASVS V12; CWE‑434 | ❌ storage disabled now | On enabling uploads: validate type/size/magic bytes, store outside webroot, scan for malware, random names. |
| F5 | Deep‑link / intent input treated as untrusted | MASVS‑PLATFORM; M4 | ❌ | Validate all deep‑link params server‑side; don't act on `data.type` from push without re‑authZ. |

## G. Mobile Platform Hardening (Android + iOS)
*(OWASP MASVS‑PLATFORM, Mobile M8; NIST SP 800‑163/124; ISO A.8.9; CWE‑926/927/200)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| G1 | Minimize exported components; protect IPC | MASVS‑PLATFORM‑1; CWE‑926 | ❌ (defaults) | Set `android:exported=false` unless required; guard exported activities/receivers with permissions/signature. |
| G2 | Disable Android backup of app data | MASVS‑STORAGE; M8 | ❌ | `android:allowBackup=false`, `android:fullBackupContent`, exclude token store. |
| G3 | Network Security Config | MASVS‑NETWORK; M5 | ❌ | Ship `network_security_config.xml`: no cleartext, pin set, no user CAs in prod. |
| G4 | App integrity / anti‑fraud attestation | 800‑163; M7 | ❌ | **Play Integrity API** (Android) + **App Attest** (iOS); enforce **Firebase App Check** on the backend for both apps. |
| G5 | Root/jailbreak & emulator/hook detection | MASVS‑RESILIENCE; M7 | ❌ | Detect root/jailbreak, Frida/Xposed, debugger; degrade/deny high‑risk actions (payments, approvals). |
| G6 | Tapjacking / overlay protection | MASVS‑PLATFORM; CWE‑1021 | ❌ | `filterTouchesWhenObscured` on sensitive buttons (approve, pay). |
| G7 | Secure WebViews (if any) | MASVS‑PLATFORM; CWE‑749 | N/A now | If added: disable JS unless needed, no `file://`/universal access, validate URLs. |
| G8 | Minimum OS version & patch baseline | 800‑124; A.8.8 | 🟡 minSdk per Flutter default | Set `minSdkVersion ≥ 24` (26+ preferred); drop known‑vulnerable OS versions. |
| G9 | Least‑privilege app permissions | A.8.9; CWE‑250 | 🟡 | Request only needed permissions (camera for scan, notifications); justify each; runtime prompts. |

## H. Binary Protection / Anti‑Tampering / Resilience
*(OWASP MASVS‑RESILIENCE, Mobile M7; NIST SA‑15; ISO A.8.28/A.8.31; CWE‑656)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| H1 | Code shrinking + obfuscation | MASVS‑RESILIENCE‑3; M7 | ❌ | Enable R8/ProGuard + `flutter build --obfuscate --split‑debug‑info`; strip symbols. |
| H2 | Anti‑debugging / anti‑tamper checks | MASVS‑RESILIENCE‑1/2; M7 | ❌ | Detect debugger/tamper (checksum, signature verify); pair with G4/G5. |
| H3 | No secrets/keys hard‑coded in the binary | M1/M10; CWE‑798 | ✅ (config via `--dart‑define`; no keys in code; `firebase_options` are public IDs) | Keep; never embed API secrets/signing keys in the app. |
| H4 | Certificate‑pin + attestation for critical flows | M7 | ❌ | See D2/G4 — required for payment/approval integrity. |

## I. Backend / API Hardening
*(OWASP API4/API8/API9; ASVS V14; NIST SC‑5/CM‑6/CM‑7; ISO A.8.9/A.8.20/A.8.27; CIS 4/12/13; CWE‑770/16/1188)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| I1 | Global rate limiting / quota (anti‑DoS) | **API4**; SC‑5; CWE‑770 | ❌ | Add gateway/app rate limits per IP+identity; body‑size caps; pagination caps (some `to_list` caps exist). |
| I2 | WAF / DDoS protection at the edge | SC‑5; CIS 13 | ❌ | Front with Cloud Armor/WAF; bot protection on auth & import endpoints. |
| I3 | Secure config / hardened defaults | **API8**; CM‑6/CM‑7 | 🟡 | Disable `/docs` (OpenAPI) in prod or auth‑gate it; remove server banners; run as non‑root; read‑only FS. |
| I4 | API inventory & versioning | **API9**; CM‑8 | 🟡 contract documented (`API_CONTRACT.md`) | Version the API; retire/monitor old versions; no undocumented/debug routes in prod. |
| I5 | Least‑privilege DB account | AC‑6; CIS 5; CWE‑250 | 🟡 app connects as `postgres` (superuser) in dev | Prod: dedicated app role with only DML on its schema; separate migration & read‑only reporting roles. |
| I6 | Idempotency & replay protection | API6 | ✅ booking (per‑lead), scans (per part/station/stage) | Extend to all state‑changing POSTs that can be retried; add idempotency keys on payments. |
| I7 | Safe error handling (no stack traces/PII to client) | ASVS V7; CWE‑209 | 🟡 FastAPI detail messages | Ensure 500s return generic messages; log detail server‑side only. |
| I8 | SSRF protection on outbound calls | **API7**; CWE‑918 | 🟡 outbound to FCM/gateway/storage | Allow‑list outbound hosts; no user‑controlled URLs fetched server‑side. |

## J. Logging, Monitoring & Audit
*(OWASP ASVS V7; Mobile M8; NIST AU‑2/AU‑6/AU‑9/AU‑12, SI‑4; ISO A.8.15/A.8.16; CIS 8; CWE‑778/532/117)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| J1 | Audit log of security‑relevant actions | **AU‑2/AU‑12**; A.8.15; CIS 8 | ✅ `audit_log` (login, RBAC actions, payments, estimates, client actions, push) | Ensure logins/failures, MFA events, role changes, privilege use, exports are all captured. |
| J2 | Tamper‑resistant / append‑only audit | **AU‑9**; A.8.15; CWE‑778 | 🟡 stored in same DB | Ship to a write‑once/SIEM sink; restrict who can read/delete; the existing "purge CEO logs" job must not erase security events. |
| J3 | No secrets/PII in logs | AU‑9; CWE‑532 | ✅ OTP codes gated to dev (`OTP_DEBUG_LOG`); prod logs a masked line | Keep redacting tokens/PII everywhere; add a log‑scrub review to CI. |
| J4 | Monitoring, alerting & anomaly detection | SI‑4; DE.CM (CSF); CIS 13 | ❌ | Alert on brute force, OTP abuse, privilege escalation, mass export, geo‑anomalies. |
| J5 | Time sync & correlation ids | AU‑8 | 🟡 UTC ISO timestamps | Add request/correlation ids; NTP on hosts. |

## K. Secrets & Configuration Management
*(OWASP API8; NIST CM‑6/SA‑10/SC‑12; ISO A.8.9/A.8.24; CIS 4/16; CWE‑798/16)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| K1 | Central secrets manager | SC‑12; A.8.24 | 🟡 env vars | GCP Secret Manager/Vault; inject at runtime; audit access; auto‑rotate. |
| K2 | Separate config per environment | CM‑6 | 🟡 `--dart‑define`, `.env` | Distinct secrets per dev/stage/prod; never share prod secrets with dev/CI. |
| K3 | `.gitignore` for secrets & no secret commits | CWE‑798; CIS 4 | ✅ `.env`, native keys ignored | Add secret‑scanning (gitleaks/GitHub secret scanning) to CI. |

## L. Supply Chain / Dependency Security
*(OWASP Mobile M2; ASVS V14.2; NIST SR‑3/SA‑12, 800‑161; ISO A.5.19‑A.5.23/A.8.30; CIS 2/16; CWE‑1104/1357)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| L1 | Pin & vet dependencies (pub, pip) | **M2**; A.8.30 | 🟡 versioned pubspec/requirements | Commit lockfiles; pin ranges; review new deps. |
| L2 | SCA / vulnerability scanning of deps | SR‑3; CIS 7/16 | ❌ | Dependabot/`pip‑audit`/`osv‑scanner`/`flutter pub outdated`; fail CI on criticals. |
| L3 | Verify plugin/SDK provenance (FCM, scanner, Razorpay) | M2; SR‑4 | 🟡 | Use official SDKs only; verify signatures/checksums; SBOM. |
| L4 | Build pipeline integrity | SA‑10; SLSA | ❌ | Signed, reproducible CI builds; protected branches; no third‑party build steps handling secrets. |

## M. Privacy & Data Protection
*(OWASP MASVS‑PRIVACY, Mobile M6; NIST Privacy Framework; ISO 27701/27018/29100; **India DPDP Act 2023**; GDPR‑equivalent; CWE‑359)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| M1 | Lawful basis + consent capture | DPDP §6; 27701 | ❌ | Capture consent for processing/marketing (Meta lead ads!); consent artifact + withdrawal. |
| M2 | Data minimization & purpose limitation | MASVS‑PRIVACY; DPDP §8 | 🟡 | Collect only needed PII; avoid storing extra Infurnia/Meta fields you don't use. |
| M3 | Data‑subject rights (access/correct/erase) | DPDP §11‑13; 27701 | ❌ | Build request handling: export, correct, delete/anonymize a customer on request. |
| M4 | Privacy policy + in‑app disclosures + store data‑safety | M6; Play Data Safety | ❌ | Publish policy; complete Google Play Data Safety & Apple Privacy Nutrition labels accurately. |
| M5 | Breach notification readiness | DPDP §8(6); CSF RS | ❌ | Process to notify the Data Protection Board + affected users; timelines; runbook. |
| M6 | PII in transit/at rest protected + access‑logged | 27018; SC‑28 | 🟡 | Combine with C5/C6/J1; restrict who can query PII; log PII access. |
| M7 | Third‑party/processor agreements (FCM, Infurnia, gateway, cloud) | DPDP §8(2); A.5.19 | ❌ | DPAs with each processor; document cross‑border transfers. |

## N. Payments Security
*(OWASP API6; PCI‑DSS‑aligned (UPI/cards); NIST SC‑8; ISO A.5.14; CWE‑840/799)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| N1 | Server computes & verifies amounts | API6 | ✅ 10% booking & totals server‑side | Keep. |
| N2 | Gateway signature verification on callbacks | API10 | 🟡 Razorpay HMAC verify in reference | Enforce on live path; reject unsigned/replayed webhooks; idempotent settlement. |
| N3 | Weak manual‑UPI proof (screenshot) is fraud‑prone | API6; CWE‑840 | 🟡 manual verify by staff | Prefer gateway/UPI‑intent with server confirmation; treat screenshots as provisional, dual‑control on large amounts. |
| N4 | Never store card/PSP secrets in app or DB | PCI; CWE‑312 | ✅ no card data stored | Keep tokenized refs only; PSP holds sensitive data. |
| N5 | Segregate payment approval from initiation | SoD; API6 | 🟡 | Four‑eyes for verifying/refunding above a threshold (see Part 2). |

## O. Resilience, Backup & Incident Response
*(NIST CP‑9/CP‑10, IR‑4/IR‑8; ISO A.5.24‑A.5.30/A.8.13/A.8.14; CSF RS/RC; CIS 11)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| O1 | Encrypted, tested backups | CP‑9; A.8.13; CIS 11 | ❌/infra | Automated Cloud SQL backups + PITR; periodic restore tests; encrypt & isolate. |
| O2 | Incident response plan | **IR‑8**; A.5.24‑A.5.28 | ❌ | Written IR plan, roles, contacts, playbooks (account compromise, data breach, token leak). |
| O3 | Business continuity / DR | CP‑10; A.5.29/A.5.30 | ❌ | RTO/RPO targets; multi‑zone; failover runbook. |
| O4 | Logging retention for forensics | AU‑11; A.8.15 | 🟡 | Define retention (e.g., 1yr security logs); protect from tampering (J2). |

## P. Secure SDLC & Vulnerability Management
*(OWASP ASVS V1/SAMM; NIST SSDF SP 800‑218, SA‑11/SA‑15/RA‑5; ISO A.8.25‑A.8.29; CIS 16; CWE Top 25 program)*

| # | Control | Standards | Status | Recommendation |
|---|---|---|---|---|
| P1 | SAST / secret scanning in CI | SA‑11; CIS 16 | ❌ | Add SAST (Bandit for Py, Dart analyzer + rules), gitleaks; block on high severity. |
| P2 | DAST / API fuzzing | SA‑11 | ❌ | Run ZAP/API fuzzing against staging; test authZ (BOLA/BFLA) automatically. |
| P3 | Periodic pentest + MASTG mobile test | 800‑163; A.8.29 | ❌ | Independent pentest of both apps + API before GA; retest after major changes. |
| P4 | Threat modeling | SA‑15; A.8.25 | 🟡 dual‑BFF designed for it | Document a STRIDE threat model per app + the payment/OTP flows. |
| P5 | Security requirements & training | A.6.3/A.8.28 | ❌ | Secure‑coding guidelines; developer security training; this doc as the requirements baseline. |

---

# Part 2 — Coverage by standard

### OWASP

**MASVS v2 (mobile)** — target **MASVS‑L2 + MASVS‑R** (has payments/PII):

| Category | Status | Key gaps |
|---|---|---|
| MASVS‑STORAGE | 🟡 | screenshot/backup/clipboard (C2‑C4) |
| MASVS‑CRYPTO | ✅/🟡 | JWT → asymmetric + rotation (E2/E4) |
| MASVS‑AUTH | 🟡 | **MFA (staff)**, refresh rotation/revocation, login lockout (A6‑A8) |
| MASVS‑NETWORK | 🟡 | **TLS pinning**, enforce HTTPS (D1‑D2) |
| MASVS‑PLATFORM | ❌ | exported components, deep links, tapjacking (G1/G6/F5) |
| MASVS‑CODE | 🟡 | dep scanning, input bounds (F2/L2) |
| MASVS‑RESILIENCE | ❌ | obfuscation, root/tamper, App Check (G4/G5/H1) |
| MASVS‑PRIVACY | ❌ | consent, DSR, data‑safety labels (M1‑M4) |

**Mobile Top 10 (2024):** M1 🟡(A2/H3) · M2 ❌(L*) · **M3 🟡→❌ auth/MFA** · M4 🟡(F*) · **M5 🟡 comms/pinning** · M6 ❌ privacy · **M7 ❌ binary protections** · M8 🟡 config · M9 🟡 storage · M10 ✅/🟡 crypto.

**API Security Top 10 (2023):** **API1 BOLA ✅** · API2 🟡(MFA/rotation) · API3 🟡 · **API4 ❌ rate‑limit** · API5 ✅ · API6 🟡 · API7 🟡 · API8 🟡 · API9 🟡 · API10 🟡.

**ASVS:** currently ~**L1** with notable L2 gaps (V2/V3 auth‑session, V9 pinning, V7 logging). **Target L2** for a consumer PII + payments app.

### NIST

- **SP 800‑63B (identity):** customers ≈ **AAL1** (single possession factor OTP); **staff below AAL1** (password only). **Target AAL2** (MFA) for staff, AAL2 step‑up for customer payments. (See Part 5.)
- **SP 800‑53r5 families in scope:** **AC** (access control — Part 4), **IA** (auth/MFA — Part 5), **AU** (audit ✅/🟡), **SC** (transport/crypto 🟡), **SI** (input/monitoring 🟡), **CM** (config 🟡), **CP/IR** (backup/IR ❌), **SR** (supply chain ❌), **RA** (RA‑5 scanning ❌).
- **SP 800‑163 (app vetting)** / **800‑124 (mobile device sec):** pre‑release app vetting + MDM/EMM for staff devices ❌.
- **CSF 2.0:** GV 🟡 · ID 🟡 · **PR** (protect) 🟡 · **DE** (detect/monitoring) ❌ · **RS/RC** (respond/recover) ❌.

### ISO/IEC

- **27001:2022 Annex A** — Organizational (A.5): access control/supplier/IR partly; **People (A.6):** training ❌; **Physical (A.7):** cloud‑provider inherited; **Technological (A.8):** authz/crypto/logging 🟡, backup/secure‑dev/vuln‑mgmt ❌.
- **27017 (cloud) / 27018 (PII in cloud):** enable CMEK, access logging, tenant isolation 🟡.
- **27701 (PIMS) + India DPDP Act 2023:** consent, DSR, breach notice, processor DPAs — mostly ❌ (Part 1‑M). **This is legally required for an Indian consumer app.**

### SANS

- **CIS Controls v8 (18):** 1‑2 inventory 🟡 · 3 data protection 🟡 · **4 secure config 🟡** · **5‑6 account/access mgmt 🟡→ Part 4/5** · 7 vuln mgmt ❌ · **8 audit logs ✅/🟡** · 10 malware (uploads) ❌ · 11 recovery ❌ · 12‑13 network/monitoring ❌ · 14 awareness ❌ · 16 app‑sec 🟡 · 18 pentest ❌.
- **CWE Top 25:** strong on **CWE‑89 (SQLi ✅)** and **CWE‑639 (IDOR ✅)**; open items **CWE‑287/306 (auth/MFA)**, **CWE‑307 (brute force)**, **CWE‑352 (CSRF — mobile uses Bearer, low, but web CRM must use tokens/anti‑CSRF)**, **CWE‑532 (secrets in logs)**, **CWE‑798 (secrets mgmt)**, **CWE‑295 (cert validation/pinning)**.

---

# Part 3 — Prioritized remediation roadmap

**P0 — do immediately (cheap, high impact):**
1. **Stop logging OTP codes / any secret** outside non‑prod (A2/J3).
2. **Enforce HTTPS** in prod builds + Android network‑security‑config; never ship the cert‑bypass ops note (D1/D3).
3. **Login brute‑force lockout + basic rate limiting** on `/auth/login` and OTP request (A3/A4/I1).
4. **Least‑privilege DB role** in prod (drop `postgres` superuser) (I5).
5. **Secrets → GCP Secret Manager**; rotate `JWT_SECRET`/DB creds; enable secret scanning (E3/K1).

**P1 — before general availability:**
6. **MFA for all staff (TOTP)**; phishing‑resistant for admins (Part 5).
7. **Refresh‑token rotation + revocation**, immediate deactivation (A6‑A8/B8).
8. **TLS pinning + Firebase App Check + Play Integrity/App Attest** (D2/G4).
9. **Segregation of privileges** redesign + admin account restrictions (Part 4).
10. **Signed URLs** for documents; private storage; upload validation (C7/F4).
11. **DPDP compliance**: consent, privacy policy, DSR, breach runbook, processor DPAs (M1‑M7).
12. **Screenshot/backup/clipboard** hardening; obfuscation; root/tamper checks (C2‑C4/G/H).
13. **Razorpay signed‑webhook** live path; dual‑control on large/refund payments (N2/N5).
14. **Dependency scanning + SAST/secret scan in CI**; pentest before launch (L2/P1‑P3).

**P2 — mature the program:**
15. Monitoring/alerting + SIEM, anomaly detection (J4).
16. Backup/restore tests, IR & DR plans (O1‑O3).
17. Field‑level PII encryption / tokenization; data classification & retention (C6/C8).
18. Threat models, security training, periodic re‑test (P3‑P5).

---

# Part 4 — Segregation & Restriction of Privileges  *(RECOMMENDATION)*

*(NIST 800‑53 **AC‑2, AC‑5 (Separation of Duties), AC‑6 (Least Privilege), AC‑6(1/2/5), IA‑2(1)**; ISO **A.5.3 (SoD), A.5.15, A.5.16, A.5.18, A.8.2 (privileged access)**; CIS **5 & 6**; OWASP **API5 BFLA**; SOX‑style controls.)*

Three principles drive this: **Least Privilege** (each identity gets the minimum
it needs), **Separation of Duties** (no single person can execute a
risk‑bearing transaction end‑to‑end), and **Privileged Access Management** (admin
power is rare, named, time‑boxed, and watched).

## 4.1 Current state — what the RBAC already does well

The 8‑role / 28‑permission model (`backend/permissions.py`) already encodes real
segregation, which is a strong base:

| Duty pair | Separated today? |
|---|---|
| Create estimate (`estimates.create`, Sales) vs **approve** (`estimates.approve`, PM/MH) | ✅ different roles |
| Submit expense (`expenses.submit`, Site Mgr) vs **approve** (`expenses.approve`, PM/MH) | ✅ different roles |
| Raise ticket (Site Mgr) vs resolve (Prod. Eng.) | ✅ |
| Upload/distribute campaign leads (MH) vs work them (Sales) | ✅ |
| Hard‑delete users (`users.delete`) | ✅ CEO‑only |

## 4.2 Toxic combinations & over‑privilege to FIX

| # | Finding | Why it's a risk | Recommendation |
|---|---|---|---|
| SoD‑1 | **`payments.manage` is held by Sales** (they record/verify the booking payment) | The person who closes the sale also confirms the money → fraud / unverified activation | Move payment **verification** to a `finance`/PM role. Sales may *record* a provisional manual‑UPI payment; a different role **verifies** it (and activation triggers only on verify). Dual‑control above a ₹ threshold. |
| SoD‑2 | **`admin` = all‑but‑delete** and **`ceo` = everything** — single logins that can manage users **and** approve estimates **and** verify payments | One compromised/rogue admin can create a user, grant itself rights, approve its own estimate and confirm payment — no second pair of eyes | Split **system administration** (users, roles, settings, audit) from **business super‑powers** (approve/verify). No one login should hold both. |
| SoD‑3 | **Self‑approval possible** for `admin`/`ceo` (they hold both `estimates.create`‑equivalent reach and `estimates.approve`) | Maker = checker | Enforce in code: an approver **cannot approve an object they created/own** (`approver_id ≠ created_by`) for estimates, expenses, payments. |
| SoD‑4 | **Shared‑looking accounts** (`ceo@…`, `admin@…` seeded) | Shared creds break accountability & audit | Named individual accounts only; disable/rename generic shared logins; every actor is a real person. |
| SoD‑5 | **`oversight.silent`** (Marketing Head silent monitoring) | Covert access to others' work — privacy & abuse concern | Keep least‑privilege; **log every use** to the immutable audit; review periodically; disclose in policy. |
| SoD‑6 | App connects to Postgres as **superuser** (dev) | DB compromise = total | Least‑privilege DB roles (4.4). |

## 4.3 Recommended target — separation of duties matrix

Define **incompatible duty sets** (a single identity must never hold two in the
same set) and enforce them when composing roles:

| Duty set | Duty A | Duty B (incompatible) |
|---|---|---|
| Estimates | create/edit | approve |
| Expenses | submit | approve |
| Payments | initiate/record | verify/reconcile · refund |
| Identity | request access | grant access / manage roles |
| Administration | manage users & roles & settings | approve business transactions / verify payments |
| Audit | perform actions | administer/erase the audit log |

Concrete role adjustments:
- **Add a `finance` role** (verify payments, approve expenses, financial analytics) — distinct from Sales and from system admin.
- **Split `admin`** → `system_admin` (users, roles, settings, audit — **no** approvals/payments) and keep business approvals in `manager`/`marketing_head`/`finance`.
- **`ceo`** stays all‑powerful **but becomes break‑glass** (4.4), not a daily driver; give the CEO a normal working role for day‑to‑day.
- Enforce `approver ≠ creator` in the estimate/expense/payment transitions.

## 4.4 Restriction of privileged accounts (PAM)

| Control | Recommendation | Standard |
|---|---|---|
| **Named, individual privileged accounts** | No shared admin/CEO logins; one human ↔ one account | AC‑2; A.5.16 |
| **Separate admin identity from daily use** | Admins do normal work with a normal role; switch to a distinct privileged account only for admin tasks | **AC‑6(5)**; CIS 5.4 |
| **Break‑glass CEO/super‑admin** | Sealed credential, hardware‑MFA, used only in emergencies, **auto‑alert on every login/action**, short forced session, reviewed after use | AC‑6(2); A.8.2 |
| **Just‑in‑Time elevation** | Request → second‑person approval → **time‑boxed** grant that auto‑expires; no standing super‑admin | AC‑6(1); CIS 6.8 |
| **Four‑eyes on the most sensitive ops** | `users.delete`, role edits, payment refunds, bulk export require a second approver | AC‑5; A.5.3 |
| **Step‑up MFA for admin actions** | Re‑authenticate with a second factor before privileged actions (ties to Part 5) | IA‑2(1); AC‑6 |
| **Privileged‑action auditing + alerting** | Every privileged/role/permission change is logged to the immutable audit and alerts security | AU‑2/AU‑12; A.8.15 |
| **Immediate deprovision (leaver)** | Deactivation revokes tokens at once (fix A7/B8), keys rotated | AC‑2(3); A.5.18 |
| **Service accounts are non‑human & least‑priv** | backend→DB, backend→FCM, webhook verifiers: no interactive login, scoped, rotated | AC‑6; A.8.2 |

## 4.5 Database privilege separation

| Role | Rights | Used by |
|---|---|---|
| `ij_app` | `SELECT/INSERT/UPDATE/DELETE` on the app schema only | the running backend |
| `ij_migrate` | `DDL` (create/alter) | migrations at deploy only |
| `ij_readonly` | `SELECT` on reporting views | analytics/BI |
| break‑glass DBA | full | emergencies only, audited |

The app must **never** run as `postgres`/superuser in production (currently does in dev).

## 4.6 Access lifecycle

- **Joiner/Mover/Leaver:** provisioning requires approval; role changes on transfer; **immediate** revoke on exit.
- **Recertification:** quarterly access review — owners re‑attest each person's role; auto‑flag dormant/over‑privileged accounts (`reports_to`/`created_by` already give the graph to drive this).
- **Deny‑by‑default:** new endpoints require an explicit gate; add a CI test asserting every route declares a permission.
- **Everything privileged is logged**, and privilege escalation raises an alert (J4).

---

# Part 5 — Two‑Factor / Multi‑Factor Authentication  *(RECOMMENDATION)*

*(NIST **SP 800‑63B (AAL2), §5.1 authenticators, §5.2.2 rate‑limiting, §5.2.8 replay resistance**; OWASP **MASVS‑AUTH‑2/3**, **ASVS V2.8 (OTP) / V2.9 (crypto MFA)**, **API2**; ISO **A.5.17, A.8.5**; CIS **6.3–6.5**; CWE‑287/308/1390.)*

MFA = at least **two of**: **knowledge** (password/PIN), **possession** (device,
TOTP, security key), **inherence** (biometric). NIST **AAL2 requires MFA** and is
the right bar for a consumer‑PII + payments system.

## 5.1 Current state vs target

| Identity | Today | AAL | Target |
|---|---|---|---|
| **Employee** (Company App) | password only | **below AAL1** (single knowledge factor, no lockout) | **AAL2 — MFA mandatory**; phishing‑resistant for admins |
| **Customer** (Client App) | phone OTP (passwordless) | ~AAL1 (single possession factor) | AAL1 login OK; **AAL2 step‑up** for payments/acceptance |

**Employee MFA is the single most important auth gap in the system.**

## 5.2 Employees (Company App) — mandatory MFA

| Recommendation | Detail | Standard |
|---|---|---|
| **TOTP as the default second factor** | RFC 6238 authenticator app (Google/Microsoft Authenticator, Authy). Server issues a per‑user secret (encrypted at rest), QR enrollment, verify; 30s step, ±1 tolerance, **track last‑used step to block replay**, rate‑limit + lockout (reuse the OTP policy) | 800‑63B §5.1.5; ASVS V2.8; A.8.5 |
| **Phishing‑resistant MFA for admins/CEO/finance** | **FIDO2 / WebAuthn passkeys or hardware security keys** (TOTP is phishable). Require for any privileged/break‑glass account | 800‑63B AAL3‑grade; AC‑6 |
| **Backup / recovery codes** | 8–10 one‑time codes, **hashed**, single‑use, shown once at enrollment; regenerate invalidates old | 800‑63B §5.1.2 |
| **Optional push‑approval MFA** | Approve/deny via FCM with **number matching** to resist MFA‑fatigue; never allow unlimited prompts | 800‑63B; anti‑fatigue |
| **SMS OTP only as last‑resort fallback** | Discouraged (SIM‑swap/interception); **never** for admins; restricted‑only | 800‑63B §5.1.3 (RESTRICTED) |
| **Enrollment enforcement** | An un‑enrolled staff user gets a **restricted session that can only enroll MFA**; a full token requires MFA. Migration window for existing users | IA‑2; A.5.17 |

## 5.3 Customers (Client App) — second factor for high‑value actions

Phone OTP is fine to *log in*. For **money/commitment** actions, add a second
factor via **step‑up**:

| Recommendation | Detail |
|---|---|
| **Device biometric / PIN step‑up** | Gate **accept‑estimate** and **payment** with `local_auth` (Face/Touch ID or device PIN) — an *inherence/knowledge* factor on the *possession‑bound* registered device = 2 factors for that action |
| **Migrate OTP to Firebase Phone Auth** | Managed OTP + reCAPTCHA/**App Check** anti‑abuse (already on the roadmap); still single‑factor, so keep the biometric step‑up |
| **Optional account PIN** | Let customers set a knowledge factor for extra assurance |
| **Bind the session to the enrolled device** | Tie the customer token to the FCM/device id; re‑verify on a new device |

## 5.4 Step‑up (transaction) authentication matrix

Re‑prompt for a second factor (fresh, short‑lived elevation) before these — even
within an active session:

| Action | Who | Second factor |
|---|---|---|
| Approve estimate / expense | PM / MH / Finance | TOTP (or passkey) |
| **Verify payment / refund** | Finance | passkey / TOTP + (large ⇒ four‑eyes) |
| Manage users / roles / settings | system_admin | **passkey** |
| Break‑glass elevation | CEO/super‑admin | **hardware key** + alert |
| Export / bulk download PII | any | TOTP |
| Change MFA / recovery info | self | current MFA |
| Accept estimate / make payment | customer | biometric/PIN |

## 5.5 Implementation plan (maps to current code)

**Backend (`backend/`):**
1. `users` gains `mfa_enrolled`, `mfa_secret` (encrypted, not plain), `mfa_type`, `mfa_backup_codes` (hashed). Reuse the proven OTP hygiene (hash, TTL, lockout, cooldown) from `routers/auth.py`/`push.py`.
2. Endpoints: `POST /auth/mfa/enroll` (secret + otpauth QR), `POST /auth/mfa/activate` (verify first code), **login becomes two‑step** (`/auth/login` → if `mfa_enrolled` return a short *pre‑auth* token → `POST /auth/mfa/verify` → full token), `POST /auth/mfa/step-up` (returns a short‑lived elevation claim), `POST /auth/mfa/recover` (backup code), admin‑assisted reset (identity‑proofed, audited, notifies user).
3. **JWT claims:** add `amr` (methods used), `aal`, and a step‑up `elevated_until`. Gate privileged endpoints on `aal ≥ 2` and, for step‑up actions, a fresh elevation. Log all MFA events to `audit_log` (`auth.mfa_enrolled/verified/failed/step_up`).
4. TOTP verify: constant‑time compare, replay‑block last step, throttle + lockout, CSPRNG secret (≥160‑bit).

**Apps (`mobile/`):**
- **Company App:** MFA **enrollment screen** (show QR/secret), **login MFA‑challenge screen** (after password), **step‑up sheet** for sensitive actions; passkey via platform authenticator for admins.
- **Client App:** `local_auth` biometric/PIN gate on `accept‑estimate` and payment; optional PIN enrollment. `ij_core` gains `verifyMfa`, `stepUp`, `enrollMfa`.

**Recovery & anti‑abuse:** backup codes; admin reset with proofing + notification; rate‑limit + lockout on all factors; alert on repeated failures/impossible‑travel; "remember this device" (≤30 days, device‑bound) for **non‑privileged** logins only.

## 5.6 Do‑nots
- Don't accept a second factor of the **same type** as the first (two possession factors ≠ MFA).
- Don't allow MFA to be silently disabled without current‑MFA re‑auth + notification.
- Don't rely on SMS for admins; don't send the OTP/secret in logs (see A2/J3).
- MFA is **not** a substitute for the other controls (TLS pinning, App Check, device binding, rate‑limiting) — defense in depth.

---

*Owner: (assign). Review cadence: quarterly, and after any major feature or incident. This document is the security requirements baseline referenced by Part 3's roadmap.*


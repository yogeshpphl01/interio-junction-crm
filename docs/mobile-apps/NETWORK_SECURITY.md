# Transport security (TLS) for the mobile apps

Enforces HTTPS‑only, no user‑added CAs in production, and (with pinning) resists
MitM — OWASP MASVS‑NETWORK, Mobile M5; NIST SC‑8; ISO A.8.20.

`ij_core`'s `ApiClient` already **refuses a non‑HTTPS base URL in release builds**
(throws unless `IJ_API_BASE` is `https://…`). The steps below add the OS‑level
controls. Cert/public‑key **pinning** is documented separately in
`docs/security/MOBILE_SECURITY_STANDARDS.md` (D2) — wire it after these.

## Android

1. Create `android/app/src/main/res/xml/network_security_config.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Production: HTTPS only, ignore user-installed CAs. -->
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>

    <!-- Debug builds only: allow the emulator host over cleartext + user CAs
         (Flutter injects a debug overlay; keep prod locked down). -->
    <debug-overrides>
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </debug-overrides>
</network-security-config>
```

2. Reference it in `android/app/src/main/AndroidManifest.xml` on `<application>`:

```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    android:usesCleartextTraffic="false"
    ... >
```

## iOS

App Transport Security is on by default. Do **not** add
`NSAllowsArbitraryLoads`. If a specific host ever needs an exception, scope it
under `NSExceptionDomains` with `NSExceptionMinimumTLSVersion=TLSv1.2` — never
globally.

## Certificate / public-key pinning (P1-8)

Pinning stops a MitM even if a rogue/compromised CA issues a cert for your host
(OWASP MASVS-NETWORK, Mobile M5; NIST SC-8; ISO A.8.20).

**Android — native `<pin-set>` (primary, SPKI, no code).** Add to the
`base-config` in `network_security_config.xml`:

```xml
<domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="true">api.interiojunction.com</domain>
    <pin-set expiration="2027-01-01">
        <!-- SPKI SHA-256 of your leaf/intermediate. ALWAYS include a backup
             pin (e.g. your next cert or the CA intermediate) so a rotation
             cannot brick installed apps. -->
        <pin digest="SHA-256">BASE64_SPKI_PIN_PRIMARY=</pin>
        <pin digest="SHA-256">BASE64_SPKI_PIN_BACKUP=</pin>
    </pin-set>
</domain-config>
```

Compute the SPKI pin for a host:

```bash
openssl s_client -servername api.interiojunction.com -connect api.interiojunction.com:443 </dev/null 2>/dev/null \
  | openssl x509 -pubkey -noout \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary | openssl enc -base64
```

**iOS / cross-platform — `ij_core`'s `ApiClient`.** Pass certificate SHA-256
pins (base64) to enable an in-code check via Dio's `validateCertificate`:

```dart
ApiClient(
  baseUrl: base, tokenStore: store, refreshPath: '/auth/refresh',
  certSha256Pins: const ['BASE64_CERT_SHA256_PRIMARY=', 'BASE64_CERT_SHA256_BACKUP='],
  appCheckToken: () => AppCheck.currentToken,   // see below
);
```

Pins are enforced **only in release with a non-empty list**, so debug/emulator
and the default (unpinned) build are unchanged. `certSha256Pins` pins the whole
**certificate** (rotate the pin on renewal); the Android `<pin-set>` pins the
**SPKI** (survives renewal with the same key) — ship both, always with a backup.

## App attestation — Firebase App Check / Play Integrity / App Attest (P1-8)

Only genuine, unmodified installs of our apps should be able to hit the
unauthenticated abuse surface (OTP request/verify, login). The backend gate is
`backend/app_check.py`:

1. In Firebase, enable **App Check** with **Play Integrity** (Android) and
   **App Attest / DeviceCheck** (iOS) providers.
2. In each app, initialise App Check at startup and pass its token to
   `ApiClient(appCheckToken: …)` — it is sent as `X-Firebase-AppCheck`.
3. On the backend set:
   - `APP_CHECK_ENABLED=1`
   - `APP_CHECK_PROJECT_NUMBER=<your Firebase project number>` (pins aud/iss)
   - optionally `APP_CHECK_JWKS_URL` (defaults to Google) or
     `APP_CHECK_JWKS_JSON` to pin the keys inline.
4. Requires `cryptography` (in `requirements-runtime.txt`) for RS256
   verification — the gate **fails closed** if it is missing or the token is
   invalid/expired/wrong-audience. Keep it **off** until every app build sends a
   valid token, or logins will 403.

## Reminders

- Ship release builds with `--dart-define=IJ_API_BASE=https://<your-api-host>/api`.
- The backend already **rejects cleartext in production** (`ENFORCE_HTTPS`, via
  `X-Forwarded-Proto`) and sends HSTS + `X-Content-Type-Options` /
  `X-Frame-Options` / `Referrer-Policy` / `Cache-Control:no-store`.
- Never ship the proxy/cert‑bypass developer note to production.

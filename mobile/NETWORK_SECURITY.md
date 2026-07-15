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

## Reminders

- Ship release builds with `--dart-define=IJ_API_BASE=https://<your-api-host>/api`.
- The backend already **rejects cleartext in production** (`ENFORCE_HTTPS`, via
  `X-Forwarded-Proto`) and sends HSTS + `X-Content-Type-Options` /
  `X-Frame-Options` / `Referrer-Policy` / `Cache-Control:no-store`.
- Never ship the proxy/cert‑bypass developer note to production.

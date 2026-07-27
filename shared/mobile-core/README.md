# mobile-core (`ij_core`)

The **shared Flutter package** behind both mobile apps
([`apps/customer-mobile`](../../apps/customer-mobile) and
[`apps/staff-mobile`](../../apps/staff-mobile)). The dual-BFF API contract is
implemented **once**, here, and both apps depend on it.

> The Dart package name is **`ij_core`** — apps import it as `package:ij_core/…`.
> Each app references this folder with `path: ../../shared/mobile-core` in its
> `pubspec.yaml`. (The folder was renamed for clarity; the package name stayed
> the same, so no imports changed.)

## What's in `lib/`

```
lib/
├── ij_core.dart           the package's public surface (barrel — exports the below)
└── src/
    ├── api/               ApiClient — Bearer injection, refresh-on-401,
    │                      optional TLS cert pinning
    ├── auth/              token storage + auth repositories (customer phone-OTP,
    │                      staff email/password + MFA + step-up + change-password)
    ├── models/            typed request/response models
    ├── security/          biometric/device step-up, secure-screen, tap guards
    ├── config.dart        environment config (API base URL, flags)
    └── data_repository.dart   ClientRepository + CompanyRepository (typed API calls)
```

## Why a shared package

Both apps hit the **same backend** with the **same auth/refresh semantics** — only
the token namespace and refresh path differ (customer vs staff). Keeping the
client, models and repositories here means a contract change is made in one place,
and both apps stay in lock-step.

Consumed via a local `path:` dependency; not published to pub.dev.

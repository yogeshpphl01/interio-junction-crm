# Interio Junction — Mobile Apps

Two Flutter apps on one FastAPI backend, following the dual-BFF boundary in
`docs/mobile-apps/API_CONTRACT.md`:

- **`apps/client_app`** — the customer app. Phone + OTP login, view/accept
  estimates, follow design/payments/project.
- **`apps/company_app`** — the employee app. Email/password login, role-aware
  work queue, run the pipeline.
- **`packages/ij_core`** — shared Dart: API client (with token auto-refresh),
  secure token storage, auth repositories, and models. Both apps depend on it, so
  the contract is implemented once.

```
mobile/
├── packages/ij_core/          # shared: api_client, token_store, auth, models
├── apps/client_app/           # customer app  (customer_access identity)
└── apps/company_app/          # employee app  (access identity)
```

> **Status: scaffolding.** This is a runnable skeleton wired to the API contract —
> the shared core, both auth flows, and both home screens. There is **no Flutter
> SDK in the CI environment where this was generated**, so it has not been
> `flutter pub get`/compiled here; do that on a machine with Flutter (see Setup).
> Screens beyond the home feed are stubs to fill in against the contract.

---

## Setup

Prerequisites: Flutter 3.22+ (Dart 3.4+).

```bash
# 1) Shared package
cd mobile/packages/ij_core && flutter pub get

# 2) Each app
cd ../../apps/client_app  && flutter pub get
cd ../company_app         && flutter pub get

# 3) Point the app at your backend (defaults to the Android-emulator host loopback)
flutter run --dart-define=IJ_API_BASE=http://10.0.2.2:8000/api      # Android emulator
flutter run --dart-define=IJ_API_BASE=http://localhost:8000/api     # iOS simulator / web
flutter run --dart-define=IJ_API_BASE=https://api.yourhost.com/api  # staging/prod
```

`10.0.2.2` is how the Android emulator reaches `localhost` on the host machine.

---

## Firebase (later — needs your project)

Both apps are structured for Firebase but do **not** require it to run the core
flows today (OTP delivery and push are backend-stubbed per the contract). When you
create the Firebase project:

1. `dart pub global activate flutterfire_cli && flutterfire configure` in each app
   → generates `firebase_options.dart` and the native config files.
2. Add `firebase_core` + `firebase_messaging` (already listed, commented, in each
   `pubspec.yaml`), then uncomment the `PushService` wiring in `main.dart`.
3. On login, the app calls `POST /client/devices` (or `/devices`) with the FCM
   token — the backend seam is already live (see the contract §6).

Phone auth: today the app uses the backend OTP endpoints. To move to Firebase
phone-auth, swap `AuthRepository.verifyOtp` to sign in with Firebase and send the
Firebase ID token to `verify-otp` — the backend change is one function (contract §10).

---

## How this maps to the contract

| App flow | Endpoint(s) |
|----------|-------------|
| Client login | `POST /client/auth/request-otp` → `verify-otp` → `refresh` |
| Client home | `GET /client/projects` |
| Client estimates / accept | `GET /client/estimates`, `POST /client/estimates/{id}/accept` |
| Company login | `POST /auth/login` → `refresh` |
| Company home | `GET /me/worklist` |
| Push registration | `POST /client/devices` · `POST /devices` |

The `ApiClient` injects the Bearer token and transparently refreshes it on a
`401`, so screens just call typed repository methods.

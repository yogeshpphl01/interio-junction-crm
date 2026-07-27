# Interio Junction — Staff Mobile (Company App)

The **staff** app for phones (Flutter): built for the field and the floor —
production and site operations on the go. The mobile counterpart of
[`../staff-web`](../staff-web), against the same [`backend`](../../backend).

- **Who logs in:** your team (staff), with **email + password** and optional
  **MFA (TOTP)**; sensitive actions use a fresh **step-up**.
- **What they can do:** a role-aware **work queue** (approvals, follow-ups,
  tickets), **projects & production** (parts, cut lists, **QR scanning** through
  stages, checklists, loading reconciliation), submit expenses/tickets, change
  their **password** (with the email+phone OTP reset), and — for admins — action
  the **DPDP erasure queue**.
- **Identity:** uses the `access` (staff) token family — separate from customers.

## Stack

Flutter (Material 3, Dart). Shares all API/auth/model code with the customer app
through the [`ij_core`](../../shared/mobile-core) package (`path:
../../shared/mobile-core` in `pubspec.yaml`).

## What's in `lib/`

```
lib/
├── main.dart              app entry — wires services + login
└── src/
    ├── auth/              email/password login, MFA screens, change-password
    ├── home/             the signed-in shell + tabs (work queue, projects),
    │                     production screens (cutlist, checklists), erasure queue
    ├── push/             FCM push wiring (off until Firebase is configured)
    └── services.dart     service locator (ApiClient + repositories, staff token)
```

## Run

No Flutter SDK is bundled in this repo's CI, so build on a machine with Flutter
(3.22+). One-time platform-folder generation + deps, then run:

```bash
flutter create .          # generates android/ ios/ … (git-ignored)
flutter pub get
flutter run --dart-define=IJ_API_BASE=http://10.0.2.2:8000/api   # Android emulator
```

Full mobile setup (both apps, Firebase, push): see
[`../../docs/mobile-apps/MOBILE_APPS_OVERVIEW.md`](../../docs/mobile-apps/MOBILE_APPS_OVERVIEW.md).

# Interio Junction — Customer Mobile

The **customer** app for phones (Flutter). The mobile counterpart of
[`../customer-web`](../customer-web): same audience, same backend, same dual-BFF
customer identity — just native.

- **Who logs in:** customers, with **phone + one-time code** (no password).
- **What they can do:** track their **project**, review & **accept estimates**,
  **approve / request changes** on designs, follow **payments**, **chat** with the
  project team, open their **documents** (via a short-lived signed link), and
  manage **privacy & consent** (view/withdraw consents, change email/phone,
  export or delete their data).
- **Identity:** uses the `customer_access` token family via the `/api/client/*`
  API — it can never reach staff routes.

## Stack

Flutter (Material 3, Dart). Shares all API/auth/model code with the staff app
through the [`ij_core`](../../shared/mobile-core) package (`path:
../../shared/mobile-core` in `pubspec.yaml`).

## What's in `lib/`

```
lib/
├── main.dart              app entry — wires services + first screen
└── src/
    ├── auth/              phone-OTP login screen
    ├── home/             the signed-in shell + tabs (projects, estimates,
    │                     designs, payments, chat) plus the Documents and
    │                     Privacy & consent screens (reached from the AppBar)
    ├── push/             FCM push wiring (off until Firebase is configured)
    └── services.dart     service locator (ApiClient + repositories, customer token)
```

## Run

CI runs `flutter analyze` and `flutter test` on every push, so the Dart is kept
compiling. To run the app itself you need a local Flutter (3.22+) and a device or
emulator. One-time platform-folder generation + deps, then run:

```bash
flutter create .          # generates android/ ios/ … (git-ignored)
flutter pub get
flutter run --dart-define=IJ_API_BASE=http://10.0.2.2:8000/api   # Android emulator
```

Full mobile setup (both apps, Firebase, push): see
[`../../docs/mobile-apps/MOBILE_APPS_OVERVIEW.md`](../../docs/mobile-apps/MOBILE_APPS_OVERVIEW.md).

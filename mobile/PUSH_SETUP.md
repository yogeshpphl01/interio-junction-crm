# Enabling Push Notifications (FCM)

The apps are **wired** for Firebase Cloud Messaging but ship with it **off**, so
they build and run today with no Firebase project. The backend push seam is
already live (`POST /client/devices`, `POST /devices`, and `send_push` wired to
estimate-share and booking — see `docs/mobile-apps/API_CONTRACT.md` §6). This
guide turns delivery on.

## How the switch works

- `lib/src/push/push_config.dart` → `const bool kFirebaseConfigured = false;`
  While `false`, `PushService` is a complete no-op: `init()` returns immediately,
  and `registerAfterLogin` / `onLogout` do nothing. The app runs normally.
- Flip it to `true` after the steps below and push turns on — no other code
  change. `PushService` then:
  1. initialises Firebase, requests notification permission;
  2. after login, sends the FCM token to the backend (`registerDevice`) and
     re-sends it on every token refresh;
  3. on logout, unregisters the token server-side and deletes it locally;
  4. routes notification taps through `main.dart`'s `onOpen` (`data['type']`).

## Steps (per app: `apps/client_app` and `apps/company_app`)

1. **Create a Firebase project** (one project can host both apps as two Firebase
   "apps"). https://console.firebase.google.com

2. **Generate config** — from each app directory:
   ```bash
   dart pub global activate flutterfire_cli
   flutterfire configure          # overwrites lib/src/push/firebase_options.dart
   ```
   This also writes the native config (`google-services.json` /
   `GoogleService-Info.plist`) and wires the Android Gradle plugin.

3. **Flip the switch** — set `kFirebaseConfigured = true` in
   `lib/src/push/push_config.dart`.

4. **Platform notes**
   - **Android 13+**: the `POST_NOTIFICATIONS` runtime permission is requested by
     `requestPermission()`; no manifest change needed for basic FCM.
   - **iOS**: enable the *Push Notifications* capability and *Background Modes →
     Remote notifications* in Xcode, and upload your APNs key to Firebase.

5. **Backend** — set the service account so the stub becomes real delivery:
   ```bash
   # Cloud Run / server env:
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
   ```
   then replace the stub in `backend/push.py::_deliver_push` with the
   `firebase_admin` multicast call (the exact snippet is in that function's
   docstring). The service-account JSON is the ONLY real secret — never ship it
   in the app.

## Building before you configure Firebase

`firebase_core`/`firebase_messaging` are listed as dependencies so the push code
compiles. Because `flutterfire configure` hasn't run yet, the Google Services
Gradle plugin isn't applied, so no `google-services.json` is required and the app
builds with push simply disabled (`kFirebaseConfigured = false`). If your
toolchain ever complains about Firebase during a pre-configuration build, either
run step 2 (recommended) or temporarily comment the two `firebase_*` lines in the
app's `pubspec.yaml` — nothing else references Firebase.

## Test it end-to-end

1. Run an app on a device/emulator with Google Play services, sign in.
2. Confirm a `device_tokens` row exists for your user/customer (backend DB).
3. Trigger a wired event — e.g. share an estimate to that customer's lead, or
   record their booking payment — and confirm the notification arrives. The
   backend also logs `notification.sent` (channel `push`) on the audit log.

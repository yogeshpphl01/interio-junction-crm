# Mobile app hardening (P1-12)

Binary + platform hardening for the Client and Company apps — OWASP
MASVS-STORAGE / MASVS-PLATFORM / MASVS-RESILIENCE, Mobile M7/M8/M9; NIST
SA-15; ISO A.8.28. Applied in code where possible (see below); the rest are
build/manifest settings to drop in at `flutter create` time.

## Already in code (ij_core / apps)

- **Screenshot / recents protection** — `SecureScreen` + `SecureScreenMixin`
  (`ij_core`). Applied to OTP login, MFA challenge, and MFA enrollment. Wire the
  native handler below to activate FLAG_SECURE; until then it no-ops safely.
  Add the mixin to any screen showing payment details or documents.
- **Keyboard-cache hygiene** — OTP and MFA code fields set
  `enableSuggestions:false`, `autocorrect:false`, `enableIMEPersonalizedLearning:false`
  so codes never enter autofill/suggestion history (C4).
- **Secrets at rest** — `flutter_secure_storage` (Keystore/Keychain) for tokens.
- **TLS** — HTTPS enforced in release; cert-pinning hook (`certSha256Pins`) and
  App Check header (see `NETWORK_SECURITY.md`).

## Android — native FLAG_SECURE handler (MethodChannel `ij_core/secure`)

In `MainActivity.kt` (each app):

```kotlin
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "ij_core/secure")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "enable" -> { window.setFlags(
                        WindowManager.LayoutParams.FLAG_SECURE,
                        WindowManager.LayoutParams.FLAG_SECURE); result.success(null) }
                    "disable" -> { window.clearFlags(
                        WindowManager.LayoutParams.FLAG_SECURE); result.success(null) }
                    else -> result.notImplemented()
                }
            }
    }
}
```

## Android — manifest & build hardening

`android/app/src/main/AndroidManifest.xml` on `<application>`:

```xml
android:allowBackup="false"
android:fullBackupContent="false"
android:dataExtractionRules="@xml/data_extraction_rules"  <!-- API 31+: exclude token store -->
android:networkSecurityConfig="@xml/network_security_config"
android:usesCleartextTraffic="false"
```
- Set `android:exported="false"` on every activity/service/receiver that does not
  need to be launched externally (G1; the launcher activity stays `true`).
- Set a modern floor: `minSdkVersion 24` (26+ preferred) in `build.gradle`.

`android/app/build.gradle` (release) — code shrink + obfuscation:

```gradle
buildTypes {
    release {
        minifyEnabled true
        shrinkResources true
        proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
    }
}
```
Build with Dart obfuscation + split symbols:
```
flutter build appbundle --obfuscate --split-debug-info=build/symbols
flutter build ipa       --obfuscate --split-debug-info=build/symbols
```

## iOS

- **Snapshot privacy**: in `AppDelegate`, blur/overlay the key window on
  `applicationWillResignActive` and remove it on `applicationDidBecomeActive`
  (iOS caches an app-switcher snapshot; FLAG_SECURE has no iOS equivalent).
- **Backups**: mark the token store item with
  `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` (already the intent of
  `flutter_secure_storage` `first_unlock_this_device`) so it is not restored to a
  new device.
- **ATS**: keep App Transport Security on; never `NSAllowsArbitraryLoads`.

## Root / jailbreak & tamper awareness (G5/H2)

- Add a detection package (e.g. `flutter_jailbreak_detection`) and, on a
  positive result, **degrade** rather than hard-block: warn, and require a fresh
  step-up (P1-9) before high-risk actions (payments, approvals, document view).
- Verify the app signature / installer source in release; pair with Play
  Integrity / App Attest (App Check gate, `NETWORK_SECURITY.md`).
- Do not put trust decisions solely on the client — the server already enforces
  authZ, four-eyes, and step-up.

## Tapjacking / overlay protection (G6)

- Android: set `android:filterTouchesWhenObscured="true"` on the sensitive view /
  theme so taps are dropped when another window overlays the app; pair with
  FLAG_SECURE (`SecureScreen`) which blocks overlays on secure windows.
- Flutter: wrap high-risk confirm buttons (accept / approve / pay) in
  `TapGuard` (ij_core) so they're consistently identified for the native flag.

## Customer biometric step-up (A9)

High-risk **customer** actions (accept estimate, approve design) can require a
fresh on-device biometric/PIN:

1. Backend: set `CLIENT_STEP_UP_ENABLED=1` (accept/approve then require the
   `X-Client-Step-Up` header).
2. App: `ij_core.Biometric.confirm()` prompts `local_auth`, calls
   `POST /client/auth/step-up`, and returns a short-lived token. Send it on the
   action, e.g.:

   ```dart
   await stepUp(bio, (h) => api.post('/client/estimates/$id/accept', headers: h));
   ```

   Add the platform bits `local_auth` needs (Android `FragmentActivity` +
   `USE_BIOMETRIC`; iOS `NSFaceIDUsageDescription`).

## Clipboard

- For any "copy code / amount" affordance, clear the clipboard a few seconds
  after the copy, and never auto-copy OTPs.

## Checklist

- [ ] MainActivity FLAG_SECURE handler wired (activates `SecureScreen`)
- [ ] `allowBackup=false` + data-extraction rules exclude the token store
- [ ] `exported=false` audited across components
- [ ] release `minifyEnabled` + `--obfuscate --split-debug-info`
- [ ] iOS snapshot blur on resign; Keychain `ThisDeviceOnly`
- [ ] root/jailbreak detection → step-up on high-risk actions
- [ ] `minSdkVersion ≥ 24`

# Enabling camera QR scanning

The part-scan sheet (`lib/src/home/projects_screen.dart` → `_ScanSheet`) works
today with **manual entry** of a part id / QR value. This adds a **camera
scanner** that fills that field.

It's delivered as a drop-in rather than pre-wired because a camera plugin's API
and native permissions can't be compile-verified in the CI environment where this
was generated — activating it is three small steps on a machine with Flutter.

## 1. Add the dependency

In `pubspec.yaml`, uncomment:

```yaml
  mobile_scanner: ^5.2.3
```

then `flutter pub get`.

## 2. Add the scanner screen

Create `lib/src/home/camera_scan_screen.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Full-screen QR/barcode scanner. Pops the first decoded value back to the
/// caller (the part-scan sheet).
class CameraScanScreen extends StatefulWidget {
  const CameraScanScreen({super.key});

  @override
  State<CameraScanScreen> createState() => _CameraScanScreenState();
}

class _CameraScanScreenState extends State<CameraScanScreen> {
  bool _done = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan QR')),
      body: MobileScanner(
        onDetect: (capture) {
          if (_done) return;
          final code = capture.barcodes.isNotEmpty
              ? capture.barcodes.first.rawValue
              : null;
          if (code != null && code.isNotEmpty) {
            _done = true;
            Navigator.pop(context, code);
          }
        },
      ),
    );
  }
}
```

## 3. Wire it into the scan sheet

In `lib/src/home/projects_screen.dart`, add the import:

```dart
import 'camera_scan_screen.dart';
```

and in `_ScanSheetState.build`, just above the "Part ID / QR value" `TextField`,
add a button that fills the field:

```dart
OutlinedButton.icon(
  onPressed: _busy ? null : () async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const CameraScanScreen()),
    );
    if (code != null && mounted) setState(() => _code.text = code);
  },
  icon: const Icon(Icons.camera_alt_outlined),
  label: const Text('Scan with camera'),
),
const SizedBox(height: 12),
```

That's it — the decoded value flows into the same `/parts/scan` call the manual
path uses.

## 4. Native permissions

- **Android**: `mobile_scanner` declares the `CAMERA` permission via its manifest;
  ensure `minSdkVersion` ≥ 21 in `android/app/build.gradle` (Flutter's default is
  fine).
- **iOS**: add to `ios/Runner/Info.plist`:

  ```xml
  <key>NSCameraUsageDescription</key>
  <string>Scan part QR codes to track production.</string>
  ```

The scanner requests the runtime permission itself on first use.

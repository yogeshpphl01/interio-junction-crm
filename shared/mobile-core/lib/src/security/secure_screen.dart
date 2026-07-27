import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Screenshot / screen-recording / app-switcher-thumbnail protection for screens
/// that show sensitive content — OTP entry, MFA codes, payment details, documents
/// (OWASP MASVS-STORAGE / MASVS-PLATFORM; Mobile M9). On Android this toggles
/// `WindowManager.FLAG_SECURE`; on iOS the host app blurs the snapshot on resign.
///
/// The Dart side is a thin MethodChannel wrapper — see `mobile/MOBILE_HARDENING.md`
/// for the tiny native handler. If the native side isn't wired yet, calls no-op
/// (MissingPluginException is swallowed), so this is safe to adopt incrementally.
class SecureScreen {
  static const MethodChannel _channel = MethodChannel('ij_core/secure');

  static Future<void> enable() => _invoke('enable');
  static Future<void> disable() => _invoke('disable');

  static Future<void> _invoke(String method) async {
    try {
      await _channel.invokeMethod(method);
    } on MissingPluginException {
      // Native handler not registered yet — fail open (no crash), see docs.
    } on PlatformException {
      // Never let a hardening hook break the screen.
    }
  }
}

/// Mix into a `State` to make a screen secure for its whole lifetime:
/// `class _X extends State<X> with SecureScreenMixin {}`.
mixin SecureScreenMixin<T extends StatefulWidget> on State<T> {
  @override
  void initState() {
    super.initState();
    SecureScreen.enable();
  }

  @override
  void dispose() {
    SecureScreen.disable();
    super.dispose();
  }
}

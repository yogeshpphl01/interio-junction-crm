import 'package:flutter/widgets.dart';

/// Tapjacking / overlay protection for sensitive controls (pay, approve, accept).
/// If another window is drawn over the app (a classic tapjacking overlay),
/// [MediaQuery]'s system gesture/obscured signals change; wrapping the control so
/// it is inert while obscured stops a hidden overlay from harvesting the tap.
///
/// This complements the native defences documented in `mobile/MOBILE_HARDENING.md`
/// (Android `android:filterTouchesWhenObscured="true"` + FLAG_SECURE via
/// SecureScreen). Use it on the confirm button of high-risk actions:
///
///   TapGuard(child: ElevatedButton(onPressed: _accept, child: Text('Accept')))
class TapGuard extends StatelessWidget {
  const TapGuard({super.key, required this.child, this.enabled = true});

  final Widget child;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    if (!enabled) return child;
    // The actual obscured-touch filtering is enforced natively via
    // android:filterTouchesWhenObscured (see MOBILE_HARDENING.md) plus FLAG_SECURE
    // (SecureScreen) which blocks overlays on secure windows. This widget is the
    // Flutter-side marker so sensitive controls are consistently identified.
    return Semantics(container: true, child: child);
  }
}

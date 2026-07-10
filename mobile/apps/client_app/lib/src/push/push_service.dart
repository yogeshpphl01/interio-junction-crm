import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'firebase_options.dart';
import 'push_config.dart';

typedef DeviceRegister = Future<void> Function(String token);
typedef OpenHandler = void Function(Map<String, dynamic> data);

/// Firebase Cloud Messaging integration, shared shape across both apps.
///
/// A complete no-op while [kFirebaseConfigured] is false, so the app builds and
/// runs with no Firebase project. Once configured it: initialises FCM, requests
/// permission, and — after login — registers the device token with the backend
/// (the `/client/devices` or `/devices` seam that is already live) and keeps it
/// fresh across token refreshes. See mobile/PUSH_SETUP.md.
class PushService {
  PushService._();
  static final PushService instance = PushService._();

  FirebaseMessaging? _fm;
  bool _ready = false;
  OpenHandler? _onOpen;

  /// Call once at startup (before runApp). Safe to call unconditionally.
  Future<void> init({OpenHandler? onOpen}) async {
    if (!kFirebaseConfigured) return; // push disabled — app runs normally
    _onOpen = onOpen;
    try {
      await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
      _fm = FirebaseMessaging.instance;
      await _fm!.requestPermission();
      FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
      // Notification tapped while the app was backgrounded:
      FirebaseMessaging.onMessageOpenedApp.listen((m) => _onOpen?.call(m.data));
      // Notification tapped from a terminated state (cold start):
      final initial = await _fm!.getInitialMessage();
      if (initial != null) _onOpen?.call(initial.data);
      _ready = true;
    } catch (_) {
      _ready = false; // never block app start on push
    }
  }

  /// Call right after a successful login: register the current token and keep it
  /// registered whenever FCM rotates it.
  Future<void> registerAfterLogin(DeviceRegister register) async {
    if (!_ready || _fm == null) return;
    try {
      final token = await _fm!.getToken();
      if (token != null) await register(token);
    } catch (_) {}
    _fm!.onTokenRefresh.listen((t) async {
      try {
        await register(t);
      } catch (_) {}
    });
  }

  /// Call on logout: unregister the token server-side, then drop it locally.
  /// Do this BEFORE clearing the auth session (the DELETE needs the token).
  Future<void> onLogout(DeviceRegister unregister) async {
    if (_fm == null) return;
    try {
      final token = await _fm!.getToken();
      if (token != null) await unregister(token);
      await _fm!.deleteToken();
    } catch (_) {}
  }
}

/// Background isolate handler (must be a top-level or static function). The OS
/// renders the notification itself; tap routing happens via onMessageOpenedApp,
/// so keep this minimal to avoid background-isolate ANRs.
@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {}

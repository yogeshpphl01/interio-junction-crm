/// Master switch for push notifications.
///
/// While `false`, [PushService] is a complete no-op — the app builds and runs
/// with no Firebase project at all. After you run `flutterfire configure`
/// (which overwrites firebase_options.dart with real values) and set up the
/// native config, flip this to `true`. See mobile/PUSH_SETUP.md.
const bool kFirebaseConfigured = false;

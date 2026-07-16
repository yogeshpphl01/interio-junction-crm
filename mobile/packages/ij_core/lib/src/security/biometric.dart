import 'package:local_auth/local_auth.dart';

import '../api/api_client.dart';

/// On-device biometric / device-PIN confirmation for high-risk **customer**
/// actions (accept estimate, approve design). On success it exchanges the local
/// check for a short-lived server elevation token, which the caller sends as the
/// `X-Client-Step-Up` header on the sensitive request. The backend enforces it
/// only when `CLIENT_STEP_UP_ENABLED` (see /client/auth/step-up). Mobile M3 /
/// NIST 800-63B step-up.
class Biometric {
  Biometric(this._api);

  final ApiClient _api;
  final LocalAuthentication _auth = LocalAuthentication();

  Future<bool> isAvailable() async =>
      await _auth.isDeviceSupported() && await _auth.canCheckBiometrics;

  /// Prompt the device biometric/PIN, then fetch a step-up token. Returns the
  /// token to attach as `X-Client-Step-Up`, or null if the user cancelled/failed.
  Future<String?> confirm({String reason = 'Confirm it\'s you to continue'}) async {
    final ok = await _auth.authenticate(
      localizedReason: reason,
      options: const AuthenticationOptions(stickyAuth: true, biometricOnly: false),
    );
    if (!ok) return null;
    final res = await _api.post('/client/auth/step-up');
    return (res is Map) ? res['step_up_token'] as String? : null;
  }
}

/// Convenience: run [action] with a fresh step-up header, or throw if declined.
/// Example: `await stepUp(bio, (h) => api.post('/client/estimates/$id/accept', headers: h));`
Future<T> stepUp<T>(Biometric bio, Future<T> Function(Map<String, String> headers) action,
    {String reason = 'Confirm it\'s you to continue'}) async {
  final token = await bio.confirm(reason: reason);
  if (token == null) {
    throw StateError('Confirmation cancelled');
  }
  return action({'X-Client-Step-Up': token});
}

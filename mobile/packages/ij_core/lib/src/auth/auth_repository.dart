import '../api/api_client.dart';
import '../models/models.dart';
import 'token_store.dart';

/// Customer (Client App) auth — phone + OTP.
class CustomerAuthRepository {
  CustomerAuthRepository(this.api, this.tokens);
  final ApiClient api;
  final TokenStore tokens;

  /// Step 1: request a login code. Always succeeds (generic, no enumeration).
  Future<void> requestOtp(String phone) async {
    await api.post('/client/auth/request-otp', body: {'phone': phone});
  }

  /// Step 2: verify the code → stores the session, returns the customer.
  Future<Session> verifyOtp(String phone, String code) async {
    final data = await api.post('/client/auth/verify-otp',
        body: {'phone': phone, 'code': code}) as Map<String, dynamic>;
    await tokens.save(
      access: data['access_token'] as String,
      refresh: data['refresh_token'] as String?,
    );
    final c = data['customer'] as Map<String, dynamic>;
    return Session(
      id: c['id'] as String,
      displayName: (c['full_name'] as String?) ?? 'You',
      raw: c,
    );
  }

  Future<void> registerDevice(String fcmToken, {String? platform}) =>
      api.post('/client/devices', body: {'token': fcmToken, 'platform': platform});

  Future<void> unregisterDevice(String fcmToken) =>
      api.delete('/client/devices', body: {'token': fcmToken});

  Future<void> logout() async {
    try {
      await api.post('/client/auth/logout');
    } finally {
      await tokens.clear();
    }
  }
}

/// Employee (Company App) auth — email + password.
class EmployeeAuthRepository {
  EmployeeAuthRepository(this.api, this.tokens);
  final ApiClient api;
  final TokenStore tokens;

  Session _session(Map<String, dynamic> u) => Session(
        id: u['id'] as String,
        displayName: (u['full_name'] as String?) ?? (u['email'] as String? ?? 'You'),
        role: u['role'] as String?,
        raw: u,
      );

  /// Password login. If MFA is enrolled the backend returns an MFA challenge
  /// instead of a session; call [verifyMfa] with the second factor to finish.
  Future<LoginResult> login(String email, String password) async {
    final data = await api.post('/auth/login',
        body: {'email': email, 'password': password}) as Map<String, dynamic>;
    if (data['mfa_required'] == true) {
      return LoginResult.mfa(data['mfa_token'] as String);
    }
    await tokens.save(
      access: data['access_token'] as String,
      refresh: data['refresh_token'] as String?,
    );
    return LoginResult.session(_session(data['user'] as Map<String, dynamic>));
  }

  /// Complete an MFA login with a TOTP or backup code.
  Future<Session> verifyMfa(String mfaToken, String code) async {
    final data = await api.post('/auth/mfa/verify',
        body: {'mfa_token': mfaToken, 'code': code}) as Map<String, dynamic>;
    await tokens.save(
      access: data['access_token'] as String,
      refresh: data['refresh_token'] as String?,
    );
    return _session(data['user'] as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> mfaStatus() async =>
      (await api.get('/auth/mfa/status')) as Map<String, dynamic>;

  /// Begin enrollment: returns {secret, otpauth_uri}.
  Future<Map<String, dynamic>> mfaEnroll() async =>
      (await api.post('/auth/mfa/enroll')) as Map<String, dynamic>;

  /// Confirm the first code to enable MFA; returns one-time backup codes.
  Future<List<String>> mfaActivate(String code) async {
    final d = await api.post('/auth/mfa/activate', body: {'code': code}) as Map<String, dynamic>;
    return ((d['backup_codes'] as List?) ?? const []).cast<String>();
  }

  Future<void> registerDevice(String fcmToken, {String? platform}) =>
      api.post('/devices', body: {'token': fcmToken, 'platform': platform});

  Future<void> unregisterDevice(String fcmToken) =>
      api.delete('/devices', body: {'token': fcmToken});

  Future<void> logout() async {
    try {
      await api.post('/auth/logout');
    } finally {
      await tokens.clear();
    }
  }
}

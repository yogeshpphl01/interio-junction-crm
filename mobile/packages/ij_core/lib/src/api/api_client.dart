import 'dart:convert' show base64;
import 'dart:io' show X509Certificate;

import 'package:crypto/crypto.dart' show sha256;
import 'package:dio/dio.dart';
import 'package:dio/io.dart' show IOHttpClientAdapter;
import 'package:flutter/foundation.dart' show kReleaseMode;

import '../auth/token_store.dart';

/// Thrown for non-2xx responses so screens can show `error.message`.
class ApiException implements Exception {
  ApiException(this.statusCode, this.message);
  final int? statusCode;
  final String message;
  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// A thin Dio wrapper that (1) injects the Bearer access token on every request
/// and (2) transparently refreshes it once on a 401, then replays the request.
/// Both apps share this; only [refreshPath] differs
/// ('/client/auth/refresh' vs '/auth/refresh').
class ApiClient {
  ApiClient({
    required String baseUrl,
    required this.tokenStore,
    required this.refreshPath,
    this.certSha256Pins = const <String>[],
    this.appCheckToken,
  }) {
    // Enforce TLS in release builds (OWASP MASVS-NETWORK / NIST SC-8). Cleartext
    // is allowed only in debug/profile (e.g. the emulator's http://10.0.2.2).
    if (kReleaseMode && !baseUrl.startsWith('https://')) {
      throw StateError('Refusing a non-HTTPS API base URL in a release build: $baseUrl '
          '(pass --dart-define=IJ_API_BASE=https://…).');
    }
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      // We interpret status codes ourselves so the interceptor can catch 401s.
      validateStatus: (_) => true,
      contentType: 'application/json',
    ));
    _installCertPinning();
    _dio.interceptors.add(InterceptorsWrapper(onRequest: (options, handler) async {
      final token = await tokenStore.readAccess();
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      // App-attestation header (Firebase App Check / Play Integrity / App Attest).
      // The backend's app_check gate verifies it on the pre-auth abuse surface.
      final ac = appCheckToken?.call();
      if (ac != null && ac.isNotEmpty) {
        options.headers['X-Firebase-AppCheck'] = ac;
      }
      handler.next(options);
    }));
  }

  /// Optional TLS certificate pinning (OWASP MASVS-NETWORK / M5). Supply the
  /// SHA-256 of the server leaf/intermediate certificate(s) (base64). Pins are
  /// enforced only in release with a non-empty list, so debug/emulator builds
  /// and the default (unpinned) configuration are unaffected. Android's native
  /// `<pin-set>` (SPKI) in network_security_config.xml is the primary mechanism;
  /// this covers iOS and gives a second, in-code line of defence. Always ship a
  /// backup pin so a cert rotation cannot brick the app.
  void _installCertPinning() {
    if (!kReleaseMode || certSha256Pins.isEmpty) return;
    final allowed = certSha256Pins.toSet();
    _dio.httpClientAdapter = IOHttpClientAdapter(
      validateCertificate: (X509Certificate? cert, String host, int port) {
        if (cert == null) return false;
        final fingerprint = base64.encode(sha256.convert(cert.der).bytes);
        return allowed.contains(fingerprint);
      },
    );
  }

  late final Dio _dio;
  final TokenStore tokenStore;
  final String refreshPath;

  /// SHA-256 (base64) of the server certificate(s) to pin. Empty = no pinning.
  final List<String> certSha256Pins;

  /// Returns the current Firebase App Check / attestation token, or null. Called
  /// per request so a refreshed token is always sent.
  final String? Function()? appCheckToken;

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _send('GET', path, query: query);

  Future<dynamic> post(String path, {Object? body}) =>
      _send('POST', path, body: body);

  Future<dynamic> patch(String path, {Object? body}) =>
      _send('PATCH', path, body: body);

  Future<dynamic> delete(String path, {Object? body}) =>
      _send('DELETE', path, body: body);

  Future<dynamic> _send(String method, String path,
      {Object? body, Map<String, dynamic>? query, bool isRetry = false}) async {
    final res = await _dio.request(
      path,
      data: body,
      queryParameters: query,
      options: Options(method: method),
    );
    final code = res.statusCode ?? 0;

    if (code == 401 && !isRetry && await _tryRefresh()) {
      return _send(method, path, body: body, query: query, isRetry: true);
    }
    if (code >= 200 && code < 300) return res.data;

    final detail = (res.data is Map && res.data['detail'] != null)
        ? res.data['detail'].toString()
        : 'Request failed';
    throw ApiException(code, detail);
  }

  /// Exchange the refresh token for a new access token. Returns false (and clears
  /// the session) if the refresh token is missing or rejected → caller lands the
  /// user back on the login screen.
  Future<bool> _tryRefresh() async {
    final refresh = await tokenStore.readRefresh();
    if (refresh == null) return false;
    final res = await _dio.post(refreshPath, data: {'refresh_token': refresh});
    if (res.statusCode == 200 && res.data is Map && res.data['access_token'] != null) {
      await tokenStore.save(access: res.data['access_token'] as String);
      return true;
    }
    await tokenStore.clear();
    return false;
  }
}

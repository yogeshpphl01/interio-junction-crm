import 'package:dio/dio.dart';
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
    _dio.interceptors.add(InterceptorsWrapper(onRequest: (options, handler) async {
      final token = await tokenStore.readAccess();
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      handler.next(options);
    }));
  }

  late final Dio _dio;
  final TokenStore tokenStore;
  final String refreshPath;

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

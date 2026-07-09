import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure, per-app token storage. The [namespace] ("client" vs "company") keeps
/// the two identity worlds' tokens separate even if both apps ever run on one
/// device — mirroring the backend's dual-BFF boundary.
class TokenStore {
  TokenStore(this.namespace);

  final String namespace;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  String get _accessKey => '$namespace.access';
  String get _refreshKey => '$namespace.refresh';

  Future<void> save({required String access, String? refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    if (refresh != null) {
      await _storage.write(key: _refreshKey, value: refresh);
    }
  }

  Future<String?> readAccess() => _storage.read(key: _accessKey);
  Future<String?> readRefresh() => _storage.read(key: _refreshKey);

  Future<bool> get hasSession async => (await readAccess()) != null;

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}

import 'package:ij_core/ij_core.dart';

/// Tiny service locator: one place that wires the shared core for the Client App.
/// The refresh path and token namespace mark this as the *customer* identity.
class Services {
  Services._();
  static final Services i = Services._();

  final TokenStore tokens = TokenStore('client');

  late final ApiClient api = ApiClient(
    baseUrl: IjConfig.fromEnv.baseUrl,
    tokenStore: tokens,
    refreshPath: '/client/auth/refresh',
  );

  late final CustomerAuthRepository auth = CustomerAuthRepository(api, tokens);
  late final ClientRepository data = ClientRepository(api);
}

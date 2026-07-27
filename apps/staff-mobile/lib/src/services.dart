import 'package:ij_core/ij_core.dart';

/// Service locator for the Company App. The 'company' token namespace and the
/// '/auth/refresh' path mark this as the *employee* identity.
class Services {
  Services._();
  static final Services i = Services._();

  final TokenStore tokens = TokenStore('company');

  late final ApiClient api = ApiClient(
    baseUrl: IjConfig.fromEnv.baseUrl,
    tokenStore: tokens,
    refreshPath: '/auth/refresh',
  );

  late final EmployeeAuthRepository auth = EmployeeAuthRepository(api, tokens);
  late final CompanyRepository data = CompanyRepository(api);
}

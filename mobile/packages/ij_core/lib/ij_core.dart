/// Shared core for the Interio Junction mobile apps: API client (with token
/// auto-refresh), secure token storage, auth repositories, data repositories,
/// and models. See docs/mobile-apps/API_CONTRACT.md.
library ij_core;

export 'src/config.dart';
export 'src/api/api_client.dart';
export 'src/auth/token_store.dart';
export 'src/auth/auth_repository.dart';
export 'src/data_repository.dart';
export 'src/models/models.dart';

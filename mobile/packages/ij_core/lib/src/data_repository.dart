import 'api/api_client.dart';
import 'models/models.dart';

/// Client App data reads/actions (customer identity).
class ClientRepository {
  ClientRepository(this.api);
  final ApiClient api;

  Future<List<ClientProject>> projects() async {
    final data = await api.get('/client/projects') as Map<String, dynamic>;
    return ((data['projects'] as List?) ?? const [])
        .cast<Map<String, dynamic>>()
        .map(ClientProject.fromJson)
        .toList();
  }

  Future<List<Map<String, dynamic>>> estimates() async {
    final data = await api.get('/client/estimates') as Map<String, dynamic>;
    return ((data['estimates'] as List?) ?? const []).cast<Map<String, dynamic>>();
  }

  Future<void> acceptEstimate(String estimateId) =>
      api.post('/client/estimates/$estimateId/accept');

  Future<Map<String, dynamic>> payments() async =>
      (await api.get('/client/payments')) as Map<String, dynamic>;

  Future<List<Map<String, dynamic>>> designs() async {
    final data = await api.get('/client/designs') as Map<String, dynamic>;
    return ((data['designs'] as List?) ?? const []).cast<Map<String, dynamic>>();
  }
}

/// Company App data reads (employee identity).
class CompanyRepository {
  CompanyRepository(this.api);
  final ApiClient api;

  Future<List<WorklistBucket>> worklist() async {
    final data = await api.get('/me/worklist') as Map<String, dynamic>;
    return ((data['buckets'] as List?) ?? const [])
        .cast<Map<String, dynamic>>()
        .map(WorklistBucket.fromJson)
        .toList();
  }
}

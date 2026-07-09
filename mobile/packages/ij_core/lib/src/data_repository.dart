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

  Future<void> approveDesign(String revId) =>
      api.post('/client/designs/$revId/approve');

  Future<void> requestDesignChanges(String revId, String feedback) =>
      api.post('/client/designs/$revId/request-changes', body: {'feedback': feedback});
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

  // --- Worklist actions (contract §5.4 / §5.6 / §5.8) ---
  Future<void> approveEstimate(String id) => api.post('/estimates/$id/approve');
  Future<void> rejectEstimate(String id) => api.post('/estimates/$id/reject');
  // Send an explicit {} so the optional DecisionIn body parses cleanly (an empty
  // application/json body can 422 on some Starlette versions).
  Future<void> approveExpense(String id) => api.post('/expenses/$id/approve', body: {});
  Future<void> rejectExpense(String id) => api.post('/expenses/$id/reject', body: {});

  Future<void> resolveTicket(String id, {String? note, bool remanufacture = false}) =>
      api.post('/tickets/$id/resolve', body: {'note': note, 'remanufacture': remanufacture});
}

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

  // --- Projects + production (contract §5.3 / §5.5) ---
  Future<List<Map<String, dynamic>>> projects() async {
    final d = await api.get('/projects') as Map<String, dynamic>;
    return ((d['projects'] as List?) ?? const []).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> project(String id) async =>
      (await api.get('/projects/$id')) as Map<String, dynamic>;

  Future<List<Map<String, dynamic>>> parts(String projectId, {String? status}) async {
    final d = await api.get('/projects/$projectId/parts',
        query: status == null ? null : {'status': status});
    return (d as List).cast<Map<String, dynamic>>();
  }

  /// Advance a part by scanning its Infurnia QR (by part_uid or qr_value).
  Future<Map<String, dynamic>> scanPart({
    String? partUid,
    String? qrValue,
    required String station,
    required String toStage,
    String result = 'pass',
    String? note,
  }) async =>
      (await api.post('/parts/scan', body: {
        'part_uid': partUid,
        'qr_value': qrValue,
        'station': station,
        'to_stage': toStage,
        'result': result,
        'note': note,
      })) as Map<String, dynamic>;

  Future<void> submitExpense({
    required String projectId,
    required num amount,
    String? note,
  }) =>
      api.post('/expenses', body: {'project_id': projectId, 'amount': amount, 'note': note});

  Future<void> raiseTicket({
    required String projectId,
    required String kind,
    required String title,
    String? partUid,
    String? description,
  }) =>
      api.post('/tickets', body: {
        'project_id': projectId,
        'kind': kind,
        'title': title,
        'part_uid': partUid,
        'description': description,
      });

  /// Ingest an Infurnia cut list (parts + QR). Idempotent per part_uid; returns
  /// {cutlist_id, created, skipped, part_count}.
  Future<Map<String, dynamic>> ingestCutlist({
    required String projectId,
    String? infurniaRef,
    required List<Map<String, dynamic>> parts,
  }) async =>
      (await api.post('/cutlists', body: {
        'project_id': projectId,
        'source': 'infurnia',
        'infurnia_ref': infurniaRef,
        'parts': parts,
      })) as Map<String, dynamic>;

  // --- Checklists + reconciliation (contract §5.7) ---
  Future<List<Map<String, dynamic>>> checklists(String projectId, {String? type}) async {
    final d = await api.get('/checklists',
        query: {'project_id': projectId, if (type != null) 'type': type});
    return (d as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> checklist(String id) async =>
      (await api.get('/checklists/$id')) as Map<String, dynamic>;

  Future<Map<String, dynamic>> createChecklist(
          String projectId, String type, List<String> items) async =>
      (await api.post('/checklists',
          body: {'project_id': projectId, 'type': type, 'items': items})) as Map<String, dynamic>;

  /// The backend takes `label` as a query parameter, not a body.
  Future<Map<String, dynamic>> addChecklistItem(String checklistId, String label) async =>
      (await api.post('/checklists/$checklistId/items?label=${Uri.encodeQueryComponent(label)}'))
          as Map<String, dynamic>;

  Future<void> setChecklistItemChecked(String checklistId, String itemId, bool checked) =>
      api.patch('/checklists/$checklistId/items/$itemId', body: {'checked': checked});

  Future<Map<String, dynamic>> completeChecklist(String id, {String? signatureRef}) async =>
      (await api.post('/checklists/$id/complete', body: {'signature_ref': signatureRef}))
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> reconciliation(String projectId) async =>
      (await api.get('/projects/$projectId/loading-reconciliation')) as Map<String, dynamic>;

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

// Typed models for the mobile-critical responses. Everything here mirrors the
// shapes in docs/mobile-apps/API_CONTRACT.md. Less-structured payloads (e.g. the
// varied worklist bucket items) stay as Map<String, dynamic>.

/// A customer's project card — `GET /client/projects`.
class ClientProject {
  ClientProject({
    required this.leadId,
    required this.fullName,
    required this.stage,
    required this.stageName,
    required this.stageColor,
    required this.status,
    this.lifecyclePhase,
    this.bhkType,
    this.requirements,
    this.project,
  });

  final String leadId;
  final String? fullName;
  final int stage;
  final String stageName;
  final String? stageColor;
  final String? status;
  final String? lifecyclePhase;
  final String? bhkType;
  final String? requirements;
  final ProjectStatus? project; // null until the booking activates it

  factory ClientProject.fromJson(Map<String, dynamic> j) => ClientProject(
        leadId: j['lead_id'] as String,
        fullName: j['full_name'] as String?,
        stage: (j['stage'] as num?)?.toInt() ?? 1,
        stageName: j['stage_name'] as String? ?? '',
        stageColor: j['stage_color'] as String?,
        status: j['status'] as String?,
        lifecyclePhase: j['lifecycle_phase'] as String?,
        bhkType: j['bhk_type'] as String?,
        requirements: j['requirements'] as String?,
        project: j['project'] == null
            ? null
            : ProjectStatus.fromJson(j['project'] as Map<String, dynamic>),
      );
}

class ProjectStatus {
  ProjectStatus({
    required this.projectCode,
    required this.contractValue,
    required this.bookingPaid,
    required this.inProduction,
    this.activatedAt,
  });

  final String? projectCode;
  final num? contractValue;
  final bool bookingPaid;
  final bool inProduction;
  final String? activatedAt;

  factory ProjectStatus.fromJson(Map<String, dynamic> j) => ProjectStatus(
        projectCode: j['project_code'] as String?,
        contractValue: j['contract_value'] as num?,
        bookingPaid: j['booking_paid'] == true,
        inProduction: j['in_production'] == true,
        activatedAt: j['activated_at'] as String?,
      );
}

/// A Company App home-feed bucket — `GET /me/worklist`.
class WorklistBucket {
  WorklistBucket({
    required this.key,
    required this.label,
    required this.action,
    required this.count,
    required this.items,
  });

  final String key;
  final String label;
  final String action;
  final int count;
  final List<Map<String, dynamic>> items;

  factory WorklistBucket.fromJson(Map<String, dynamic> j) => WorklistBucket(
        key: j['key'] as String,
        label: j['label'] as String,
        action: j['action'] as String? ?? '',
        count: (j['count'] as num?)?.toInt() ?? 0,
        items: ((j['items'] as List?) ?? const [])
            .cast<Map<String, dynamic>>(),
      );
}

/// The signed-in identity (either a customer or an employee).
class Session {
  Session({required this.id, required this.displayName, this.role, this.raw});
  final String id;
  final String displayName;
  final String? role; // employee only
  final Map<String, dynamic>? raw;
}

/// Result of an employee login: either a full session, or an MFA challenge that
/// must be completed with a second factor before a session is issued.
class LoginResult {
  LoginResult.session(this.session) : mfaToken = null;
  LoginResult.mfa(this.mfaToken) : session = null;

  final Session? session;
  final String? mfaToken;

  bool get mfaRequired => mfaToken != null;
}

"""
<module name="pg_schema" layer="persistence">
  <purpose>
    Declarative registry that describes how every former MongoDB "collection"
    is represented as a real PostgreSQL table. This file is the single source of
    truth for the physical database shape that lives in your Hostinger / pgAdmin
    PostgreSQL server.
  </purpose>

  <why-typed-columns>
    The original CRM stored each record as a free-form MongoDB document. We could
    have dumped each document into a single JSONB column, but that would make the
    data almost unreadable inside pgAdmin. Instead, every well-known field becomes
    a proper, typed SQL column so you can run normal SQL reports
    (e.g. SELECT full_name, stage, lifecycle_phase FROM leads WHERE city = 'Pune').
    Any unexpected / dynamic key that is not declared here is transparently stored
    in a catch-all `extra JSONB` column, so nothing is ever lost.
  </why-typed-columns>

  <contract>
    Each entry of SCHEMA maps a collection-name -> table-definition:
      pk       : name of the primary-key column.
      columns  : ordered dict of column-name -> SQL type. (extra JSONB is added
                 automatically to every table by the data layer.)
      json     : list of columns whose Python value is a dict/list and must be
                 stored as JSONB (round-tripped as native Python objects).
      indexes  : list of {cols: [(name, direction)], unique: bool} index specs.
                 direction 1 = ASC, -1 = DESC.
  </contract>

  <timestamps-note>
    created_at / updated_at and friends are intentionally kept as TEXT holding
    ISO-8601 UTC strings. The original code compares them lexicographically
    (e.g. {"created_at": {"$gte": today_iso}}); ISO-8601 UTC sorts correctly as
    text, so keeping TEXT preserves the exact original behaviour 1:1.
  </timestamps-note>
</module>
"""

# <section name="Lead lifecycle / journey vocabulary">
#   <description>
#     New in this iteration. These constants describe the high-level "journey
#     bucket" a lead falls into, independent of the 6 granular pipeline stages.
#     They answer the business question: did this person only enquire, did they
#     walk part-way with us and drop off, or did we complete their project?
#   </description>
# </section>
LIFECYCLE_PHASES = [
    "Enquiry",       # captured/qualified only — never progressed past first contact
    "In-Progress",   # actively moving through the middle of the pipeline
    "Completed",     # full journey finished — project sent to factory / delivered
    "Dropped",       # explicitly Lost or went cold after partial progress
    "On-hold",       # paused by the client / us
]

# <constant name="EXTRA_COLUMN">
#   <why>Name of the JSONB overflow column appended to every table.</why>
# </constant>
EXTRA_COLUMN = "extra"


# <section name="SCHEMA registry">
#   <description>One declaration per collection used anywhere in the backend.</description>
# </section>
SCHEMA: dict[str, dict] = {
    # <table name="users"><purpose>Authentication + RBAC principals.</purpose></table>
    "users": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "email": "TEXT",
            "password_hash": "TEXT",
            "full_name": "TEXT",
            "role": "TEXT",
            "phone": "TEXT",
            "recovery_email": "TEXT",            # personal inbox for password-reset OTPs
            "is_active": "BOOLEAN",
            "must_change_password": "BOOLEAN",  # set after admin generates a password
            "created_by": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("email", 1)], "unique": True},
        ],
    },

    # <table name="password_resets">
    #   <purpose>
    #     Short-lived one-time-password (OTP) records for the self-service
    #     "forgot password" flow. The app generates a 4-digit code, stores only its
    #     bcrypt hash here with an expiry + attempt counter, and delivers the plain
    #     code to the user's recovery_email (pluggable: email now, SMS later).
    #     "Latest row wins" — only the most recent, unconsumed row for a user is
    #     ever honoured, so older codes are automatically void.
    #   </purpose>
    # </table>
    "password_resets": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "user_id": "TEXT",
            "otp_hash": "TEXT",       # bcrypt hash of the code (never the plain code)
            "expires_at": "TEXT",
            "attempts": "INTEGER",    # wrong tries so far (locks at OTP_MAX_ATTEMPTS)
            "sent_at": "TEXT",        # last delivery time (drives the resend cooldown)
            "consumed": "BOOLEAN",    # used / invalidated
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("user_id", 1)], "unique": False},
            {"cols": [("created_at", -1)], "unique": False},
        ],
    },

    # <table name="roles">
    #   <purpose>
    #     Account categories. Built-in roles (is_system) live here alongside any
    #     custom categories the CEO/Admin create (Module 7). Deleting a custom
    #     category sets is_deleted (the record is kept, never physically removed).
    #   </purpose>
    # </table>
    "roles": {
        "pk": "key",
        "columns": {
            "key": "TEXT",
            "label": "TEXT",
            "color": "TEXT",
            "base_role": "TEXT",       # built-in role a custom category mirrors (optional)
            "permissions": "JSONB",    # explicit permission keys
            "is_system": "BOOLEAN",    # built-in, non-deletable
            "is_deleted": "BOOLEAN",   # soft-deleted custom category (record retained)
            "created_by": "TEXT",
            "created_at": "TEXT",
        },
        "json": ["permissions"],
        "indexes": [],
    },

    # <table name="leads">
    #   <purpose>The Kanban cards — one row per prospective customer.</purpose>
    #   <new-fields>
    #     journey/lifecycle columns + Meta-Lead-Ads import columns were added in
    #     this iteration. See LIFECYCLE_PHASES and the importer for how they fill.
    #   </new-fields>
    # </table>
    "leads": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            # --- core contact + brief (original fields) ---
            "full_name": "TEXT",
            "email": "TEXT",
            "phone": "TEXT",
            "city": "TEXT",
            "address": "TEXT",
            "lead_type": "TEXT",
            "source": "TEXT",
            "bhk_type": "TEXT",
            "kitchen_layout": "TEXT",
            "tentative_budget": "DOUBLE PRECISION",
            "requirements": "TEXT",
            "assigned_to": "TEXT",
            "created_by": "TEXT",
            # --- pipeline position + outcome (original fields) ---
            "stage": "INTEGER",
            "status": "TEXT",
            "project_id": "TEXT",
            "lost_reason": "TEXT",
            "won_reason": "TEXT",
            "hold_reason": "TEXT",
            "won_value": "DOUBLE PRECISION",
            "closed_at": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            # --- NEW: lead-journey tracking (high-level buckets) ---
            "lifecycle_phase": "TEXT",   # one of LIFECYCLE_PHASES
            "furthest_stage": "INTEGER", # highest pipeline stage ever reached (1..6)
            "delivered_at": "TEXT",      # when project handover/delivery happened
            # --- NEW: lead-journey tracking (granular drop-off) ---
            "dropped_stage": "INTEGER",  # stage at which the lead went cold/lost
            "dropped_at": "TEXT",
            "dropped_reason": "TEXT",
            "journey": "JSONB",          # list of per-stage entry/exit records
            # --- NEW: Meta (Facebook/Instagram) Lead-Ads import provenance ---
            "meta_lead_id": "TEXT",      # the unique "l:xxxx" id from Meta
            "source_platform": "TEXT",   # ig / fb
            "source_campaign": "TEXT",   # campaign_name from the ad
            "scope_of_work": "TEXT",     # "what's the scope of work" answer
            "project_timeline": "TEXT",  # "when would you like to start" answer
            "priority_pref": "TEXT",     # "what is most important to you" answer
            "is_organic": "BOOLEAN",
            "import_batch_id": "TEXT",   # links back to import_batches.id
        },
        "json": ["journey"],
        "indexes": [
            {"cols": [("stage", 1)], "unique": False},
            {"cols": [("assigned_to", 1)], "unique": False},
            {"cols": [("status", 1)], "unique": False},
            {"cols": [("lifecycle_phase", 1)], "unique": False},
            {"cols": [("project_id", 1)], "unique": False},
            # Unique (when present) so Excel re-uploads UPDATE instead of duplicating.
            {"cols": [("meta_lead_id", 1)], "unique": True},
        ],
    },

    # <table name="projects"><purpose>Created when a lead reaches Site Measurement.</purpose></table>
    "projects": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_code": "TEXT",
            "lead_id": "TEXT",
            "rough_estimate": "DOUBLE PRECISION",
            "contract_value": "DOUBLE PRECISION",
            "signed_off": "BOOLEAN",
            "sent_to_factory": "BOOLEAN",
            "factory_handover_at": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_code", 1)], "unique": True},
            {"cols": [("lead_id", 1)], "unique": False},
        ],
    },

    # <table name="site_measurements"><purpose>Supervisor site visits / measurements.</purpose></table>
    "site_measurements": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_id": "TEXT",
            "scheduled_at": "TEXT",
            "completed_at": "TEXT",
            "supervisor_id": "TEXT",
            "total_area_sqft": "DOUBLE PRECISION",
            "ceiling_height": "DOUBLE PRECISION",
            "status": "TEXT",
            "notes": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("supervisor_id", 1)], "unique": False},
        ],
    },

    # <table name="design_revisions"><purpose>2D/3D design iterations per project.</purpose></table>
    "design_revisions": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_id": "TEXT",
            "revision_number": "INTEGER",
            "title": "TEXT",
            "designer_id": "TEXT",
            "status": "TEXT",
            "client_feedback": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1), ("revision_number", 1)], "unique": True},
            {"cols": [("designer_id", 1)], "unique": False},
        ],
    },

    # <table name="payments"><purpose>Milestone payment rail per project.</purpose></table>
    "payments": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_id": "TEXT",
            "milestone": "TEXT",
            "amount": "DOUBLE PRECISION",
            "due_date": "TEXT",
            "paid_date": "TEXT",
            "status": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
        ],
    },

    # <table name="activities"><purpose>Per-lead timeline (calls, notes, stage changes).</purpose></table>
    "activities": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "lead_id": "TEXT",
            "type": "TEXT",
            "summary": "TEXT",
            "actor_id": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("lead_id", 1)], "unique": False},
        ],
    },

    # <table name="stage_history"><purpose>Immutable log of pipeline stage moves.</purpose></table>
    "stage_history": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "lead_id": "TEXT",
            "from_stage": "INTEGER",
            "to_stage": "INTEGER",
            "changed_by": "TEXT",
            "note": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("lead_id", 1)], "unique": False},
        ],
    },

    # <table name="documents"><purpose>File metadata (bytes live in object storage).</purpose></table>
    "documents": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_id": "TEXT",
            "type": "TEXT",
            "storage_path": "TEXT",
            "original_filename": "TEXT",
            "content_type": "TEXT",
            "size": "BIGINT",
            "uploaded_by": "TEXT",
            "linked_measurement_id": "TEXT",
            "linked_revision_id": "TEXT",
            "is_deleted": "BOOLEAN",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
        ],
    },

    # <table name="settings"><purpose>Key/value app config (score weights, notifications).</purpose></table>
    "settings": {
        "pk": "key",
        "columns": {
            "key": "TEXT",
            "value": "JSONB",
        },
        "json": ["value"],
        "indexes": [],
    },

    # <table name="automations"><purpose>Per-rule enabled flag.</purpose></table>
    "automations": {
        "pk": "key",
        "columns": {
            "key": "TEXT",
            "enabled": "BOOLEAN",
        },
        "json": [],
        "indexes": [],
    },

    # <table name="automation_signals"><purpose>Live feed of automation firings.</purpose></table>
    "automation_signals": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "event": "TEXT",
            "summary": "TEXT",
            "lead_id": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("event", 1)], "unique": False},
            {"cols": [("created_at", -1)], "unique": False},
        ],
    },

    # <table name="audit_log"><purpose>Append-only record of every meaningful action.</purpose></table>
    "audit_log": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "actor_id": "TEXT",
            "actor_email": "TEXT",
            "actor_name": "TEXT",
            "actor_role": "TEXT",
            "action": "TEXT",
            "target_type": "TEXT",
            "target_id": "TEXT",
            "target_label": "TEXT",
            "metadata": "JSONB",
            "ip": "TEXT",
            "user_agent": "TEXT",
            "created_at": "TEXT",
        },
        "json": ["metadata"],
        "indexes": [
            {"cols": [("created_at", -1)], "unique": False},
            {"cols": [("action", 1)], "unique": False},
            {"cols": [("actor_id", 1)], "unique": False},
        ],
    },

    # <table name="import_batches">
    #   <purpose>
    #     NEW. One row per Excel upload, so every imported lead can be traced back
    #     to the file/run it came from, and the UI can show an import summary.
    #   </purpose>
    # </table>
    "import_batches": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "filename": "TEXT",
            "uploaded_by": "TEXT",
            "source": "TEXT",          # e.g. "meta_lead_ads"
            "total_rows": "INTEGER",
            "created_count": "INTEGER",
            "updated_count": "INTEGER",
            "skipped_count": "INTEGER",
            "error_count": "INTEGER",
            "errors": "JSONB",         # list of {row, reason}
            "created_at": "TEXT",
        },
        "json": ["errors"],
        "indexes": [
            {"cols": [("created_at", -1)], "unique": False},
        ],
    },
}


# <function name="get_table">
#   <purpose>
#     Return the table definition for a collection. Unknown collections fall back
#     to a minimal {id + extra} shape so the data layer never hard-crashes on a
#     name that was not pre-declared.
#   </purpose>
# </function>
def get_table(name: str) -> dict:
    return SCHEMA.get(name, {"pk": "id", "columns": {"id": "TEXT"}, "json": [], "indexes": []})

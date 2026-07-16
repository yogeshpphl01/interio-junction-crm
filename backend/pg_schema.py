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
            "reports_to": "TEXT",                # manager in the hierarchy (mobile ecosystem)
            "is_active": "BOOLEAN",
            "must_change_password": "BOOLEAN",  # set after admin generates a password
            "created_by": "TEXT",
            "failed_login_count": "INTEGER",    # brute-force lockout (reset on success)
            "locked_until": "TEXT",             # ISO ts; login rejected while in the future
            # --- MFA (TOTP) ---
            "mfa_enrolled": "BOOLEAN",
            "mfa_secret": "TEXT",               # base32 TOTP secret — ENCRYPT AT REST (CMEK / field-level, C5/C6)
            "mfa_backup_codes": "JSONB",        # [{hash, used}] one-time recovery codes (bcrypt-hashed)
            "mfa_last_step": "INTEGER",         # last consumed TOTP step (replay protection)
            "token_version": "INTEGER",         # bump to instantly revoke all of a user's tokens
            "created_at": "TEXT",
        },
        "json": ["mfa_backup_codes"],
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
            # --- mobile ecosystem: campaign + hierarchy distribution (MH -> PM -> SE) ---
            "campaign_id": "TEXT",   # links to marketing_campaigns.id
            "pm_id": "TEXT",         # Project Manager the lead was distributed to
            "customer_id": "TEXT",   # links to customers.id once the client authenticates (Client App)
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
            {"cols": [("campaign_id", 1)], "unique": False},
            {"cols": [("pm_id", 1)], "unique": False},
            {"cols": [("customer_id", 1)], "unique": False},
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
            "booking_paid": "BOOLEAN",         # 10% booking received -> project activated
            "activated_at": "TEXT",
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
            "lead_id": "TEXT",                 # booking payment is recorded before the project exists
            "type": "TEXT",                    # "milestone" (web CRM) | "booking" (mobile)
            "milestone": "TEXT",
            "amount": "DOUBLE PRECISION",
            "currency": "TEXT",
            "method": "TEXT",                  # manual_upi | razorpay
            "reference": "TEXT",               # UPI txn ref / gateway payment id
            "screenshot_ref": "TEXT",          # manual-UPI payment screenshot
            "verified_by": "TEXT",
            "verified_at": "TEXT",
            "created_by": "TEXT",              # who RECORDED the milestone (four-eyes: != confirmer)
            "confirmed_by": "TEXT",            # who CONFIRMED it Paid (SoD, must differ from created_by)
            "gateway": "TEXT",                 # "razorpay" when paid via the gateway
            "gateway_order_id": "TEXT",        # Razorpay order id (set at order creation)
            "gateway_payment_id": "TEXT",      # Razorpay payment id (from the webhook)
            "refunded_at": "TEXT",             # SoD refund path (P1-13)
            "refund_amount": "DOUBLE PRECISION",
            "refunded_by": "TEXT",
            "due_date": "TEXT",
            "paid_date": "TEXT",
            "status": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("lead_id", 1)], "unique": False},
            {"cols": [("gateway_order_id", 1)], "unique": False},
        ],
    },

    # <table name="gateway_events"><purpose>Idempotency ledger for payment-gateway
    #   webhooks (P1-13). The gateway event id is the PK, so a replayed webhook is a
    #   no-op and a payment can never activate a project twice.</purpose></table>
    "gateway_events": {
        "pk": "id",
        "columns": {
            "id": "TEXT",            # the gateway's event id (idempotency key)
            "event_type": "TEXT",    # payment.captured | refund.processed | ...
            "payment_id": "TEXT",    # our payments.id it resolved to
            "processed_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("payment_id", 1)], "unique": False},
        ],
    },

    # <chat> Project chat (customer <-> staff). A thread starts as a DM and can
    #   convert to a project GROUP once the project activates. Realtime delivery
    #   (Firestore) + the Flutter UI layer on top of this REST foundation. </chat>
    "chat_threads": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_id": "TEXT",
            "lead_id": "TEXT",
            "kind": "TEXT",            # dm | group
            "title": "TEXT",
            "created_by": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("lead_id", 1)], "unique": False},
        ],
    },
    "chat_messages": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "thread_id": "TEXT",
            "sender_type": "TEXT",     # staff | customer
            "sender_id": "TEXT",
            "sender_name": "TEXT",
            "body": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("thread_id", 1)], "unique": False},
            {"cols": [("created_at", 1)], "unique": False},
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

    # <table name="fixtures">
    #   <purpose>
    #     The "Fixture" section captured at Booking (stage 4) — the hardware /
    #     lighting / appliance selections committed for a project. Linked to the
    #     project (and its lead) so it travels with the job into production.
    #   </purpose>
    # </table>
    "fixtures": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "project_id": "TEXT",
            "lead_id": "TEXT",
            "name": "TEXT",
            "category": "TEXT",
            "brand": "TEXT",
            "model": "TEXT",
            "quantity": "INTEGER",
            "unit": "TEXT",
            "notes": "TEXT",
            "created_by": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("lead_id", 1)], "unique": False},
        ],
    },

    # ========================================================================
    # <mobile-ecosystem tables>
    #   New tables for the two-app mobile ecosystem (docs/mobile-apps). Additive —
    #   the web CRM never reads them. Existing tables are reused where they fit
    #   (payments, documents, design_revisions, site_measurements, fixtures).
    # </mobile-ecosystem>
    # ========================================================================

    # <table name="marketing_campaigns"><purpose>One row per ad-campaign Excel the Marketing Head imports.</purpose></table>
    "marketing_campaigns": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "name": "TEXT", "source": "TEXT",   # e.g. facebook
            "sheet_ref": "TEXT", "uploaded_by": "TEXT", "lead_count": "INTEGER",
            "created_at": "TEXT",
        },
        "json": [], "indexes": [{"cols": [("created_at", -1)], "unique": False}],
    },

    # <table name="customers"><purpose>The customer's authenticated identity for the Client App. Phone + Email are the primary keys.</purpose></table>
    "customers": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "lead_id": "TEXT", "full_name": "TEXT",
            "phone": "TEXT", "email": "TEXT", "auth_uid": "TEXT",
            "is_active": "BOOLEAN", "last_login_at": "TEXT", "created_at": "TEXT",
            "token_version": "INTEGER",   # bump to instantly revoke the customer's tokens
            "erased_at": "TEXT",          # DPDP erasure: PII anonymized at this ts (P1-11)
            # <pii-encryption> Blind-index surrogates for the encrypted phone/email
            #   columns (HMAC of the normalized value) — carry the UNIQUE constraint
            #   and enable equality lookups when PII_ENCRYPTION_KEY is set. Unused
            #   (NULL) when encryption is off. See pii_crypto.py / C6. </pii-encryption>
            "phone_bidx": "TEXT",
            "email_bidx": "TEXT",
        },
        "json": [],
        "encrypted": ["phone", "email"],   # stored AES-GCM-encrypted; looked up via *_bidx
        "indexes": [
            {"cols": [("phone", 1)], "unique": True},   # harmless in encrypted mode (ciphertext never collides)
            {"cols": [("email", 1)], "unique": True},
            {"cols": [("phone_bidx", 1)], "unique": True},   # real uniqueness in encrypted mode
            {"cols": [("email_bidx", 1)], "unique": True},
            {"cols": [("lead_id", 1)], "unique": False},
        ],
    },
    # <dpdp> Consent ledger + erasure requests (India DPDP Act 2023 §6/§11-13). </dpdp>
    "consents": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "subject_type": "TEXT",       # "customer"
            "subject_id": "TEXT",
            "purpose": "TEXT",            # data_processing | marketing | ...
            "policy_version": "TEXT",
            "granted": "BOOLEAN",         # append-only ledger; withdrawal = new granted=false row
            "source": "TEXT",             # client_app | web | staff
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("subject_id", 1)], "unique": False},
            {"cols": [("subject_id", 1), ("purpose", 1)], "unique": False},
        ],
    },
    "erasure_requests": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "customer_id": "TEXT",
            "status": "TEXT",             # pending | completed | rejected
            "reason": "TEXT",
            "requested_at": "TEXT",
            "decided_by": "TEXT",
            "decided_at": "TEXT",
            "note": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("customer_id", 1)], "unique": False},
            {"cols": [("status", 1)], "unique": False},
        ],
    },

    # <table name="customer_otps">
    #   <purpose>
    #     One-time login codes for the Client App. Mirrors password_resets but is
    #     keyed on PHONE (not customer_id) because the customer's account may not
    #     exist yet at the moment the first code is requested. Only the hash of the
    #     code is stored; "latest row per phone wins". Delivery is pluggable
    #     (SMS / WhatsApp / Firebase later) — logged for now.
    #   </purpose>
    # </table>
    "customer_otps": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "phone": "TEXT",          # normalized phone the code was issued for
            "otp_hash": "TEXT",       # bcrypt hash of the code (never the plain code)
            "expires_at": "TEXT",
            "attempts": "INTEGER",    # wrong tries so far (locks at OTP_MAX_ATTEMPTS)
            "sent_at": "TEXT",        # last delivery time (drives the resend cooldown)
            "consumed": "BOOLEAN",    # used / invalidated
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("phone", 1)], "unique": False},
            {"cols": [("created_at", -1)], "unique": False},
        ],
    },

    # <table name="device_tokens">
    #   <purpose>
    #     FCM push registration tokens for BOTH mobile apps. owner_type +
    #     owner_id point at either a customer (Client App) or a user (Company
    #     App); the token is unique so re-registering the same device updates in
    #     place. Deactivated (not deleted) when FCM reports the token stale or the
    #     app logs out, so send_push only ever fans out to live devices.
    #   </purpose>
    # </table>
    "device_tokens": {
        "pk": "id",
        "columns": {
            "id": "TEXT",
            "owner_type": "TEXT",     # "customer" | "user"
            "owner_id": "TEXT",
            "token": "TEXT",          # FCM registration token
            "platform": "TEXT",       # android | ios | web
            "app": "TEXT",            # "client" | "company"
            "is_active": "BOOLEAN",
            "last_seen_at": "TEXT",
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("token", 1)], "unique": True},
            {"cols": [("owner_id", 1)], "unique": False},
        ],
    },

    # <table name="estimates"><purpose>Versioned estimate header; workflow draft->submitted->approved->shared->accepted->revised.</purpose></table>
    "estimates": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "lead_id": "TEXT", "project_id": "TEXT",
            "version": "INTEGER", "status": "TEXT", "currency": "TEXT",
            "subtotal": "DOUBLE PRECISION", "discount": "DOUBLE PRECISION",
            "tax": "DOUBLE PRECISION", "total": "DOUBLE PRECISION",
            "valid_until": "TEXT", "pdf_ref": "TEXT",
            "created_by": "TEXT", "approved_by": "TEXT",
            "created_at": "TEXT", "updated_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("lead_id", 1)], "unique": False},
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("status", 1)], "unique": False},
        ],
    },

    # <table name="estimate_items"><purpose>Line items of an estimate (the priced BOQ rows).</purpose></table>
    "estimate_items": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "estimate_id": "TEXT", "category": "TEXT",
            "description": "TEXT", "unit": "TEXT", "quantity": "DOUBLE PRECISION",
            "rate": "DOUBLE PRECISION", "amount": "DOUBLE PRECISION",
            "meta": "JSONB", "created_at": "TEXT",
        },
        "json": ["meta"],
        "indexes": [{"cols": [("estimate_id", 1)], "unique": False}],
    },

    # <table name="cutlists"><purpose>A cut list imported from Infurnia (PDF/Excel) per project; parent of parts.</purpose></table>
    "cutlists": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "project_id": "TEXT", "pdf_ref": "TEXT",
            "source": "TEXT",            # e.g. "infurnia"
            "infurnia_ref": "TEXT",      # Infurnia order/design reference
            "created_by": "TEXT", "part_count": "INTEGER", "created_at": "TEXT",
        },
        "json": [], "indexes": [{"cols": [("project_id", 1)], "unique": False}],
    },

    # <table name="parts">
    #   <purpose>One row per manufactured panel/part. Identity is INGESTED from
    #   Infurnia (part_uid = Infurnia's panel/part id), not minted by us — see
    #   docs/mobile-apps §14. The traceability spine for production tracking.</purpose>
    # </table>
    "parts": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "cutlist_id": "TEXT", "project_id": "TEXT",
            "part_uid": "TEXT",          # Infurnia panel/part id (matches the printed QR)
            "source": "TEXT",            # e.g. "infurnia"
            "infurnia_ref": "TEXT",      # original Infurnia panel/order id
            "name": "TEXT", "material": "TEXT", "dimensions": "TEXT",
            "quantity": "INTEGER", "status": "TEXT", "current_station": "TEXT",
            "created_at": "TEXT", "updated_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("part_uid", 1)], "unique": True},
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("cutlist_id", 1)], "unique": False},
            {"cols": [("status", 1)], "unique": False},
        ],
    },

    # <table name="qr_codes">
    #   <purpose>The DECODED value of Infurnia's printed QR per part (so our scans
    #   match), plus a reference to the Infurnia label. We do NOT generate QR.</purpose>
    # </table>
    "qr_codes": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "part_id": "TEXT", "part_uid": "TEXT",
            "qr_value": "TEXT",          # exact decoded value Infurnia's QR encodes
            "label_ref": "TEXT",         # Infurnia panel-label PDF/image reference
            "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("part_id", 1)], "unique": True},
            {"cols": [("part_uid", 1)], "unique": True},
        ],
    },

    # <table name="part_scans"><purpose>Append-only scan history — every factory/site stage transition of a part.</purpose></table>
    "part_scans": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "part_id": "TEXT", "part_uid": "TEXT", "project_id": "TEXT",
            "station": "TEXT", "from_stage": "TEXT", "to_stage": "TEXT",
            "scanned_by": "TEXT", "device_id": "TEXT", "result": "TEXT",
            "note": "TEXT", "photo_ref": "TEXT", "gps": "TEXT", "created_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("part_id", 1)], "unique": False},
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("created_at", -1)], "unique": False},
        ],
    },

    # <table name="tickets"><purpose>Site/production issues (damaged/missing/fitting) raised by Site Manager to Production Engineer.</purpose></table>
    "tickets": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "project_id": "TEXT", "part_uid": "TEXT",
            "kind": "TEXT", "priority": "TEXT", "status": "TEXT",
            "title": "TEXT", "description": "TEXT",
            "raised_by": "TEXT", "assigned_to": "TEXT",
            "created_at": "TEXT", "resolved_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("status", 1)], "unique": False},
            {"cols": [("assigned_to", 1)], "unique": False},
        ],
    },

    # <table name="ticket_media"><purpose>Photos/videos attached to a ticket.</purpose></table>
    "ticket_media": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "ticket_id": "TEXT", "kind": "TEXT",
            "storage_ref": "TEXT", "uploaded_by": "TEXT", "created_at": "TEXT",
        },
        "json": [], "indexes": [{"cols": [("ticket_id", 1)], "unique": False}],
    },

    # <table name="expenses"><purpose>Site expense bills (photo) with PM approval workflow.</purpose></table>
    "expenses": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "project_id": "TEXT", "amount": "DOUBLE PRECISION",
            "currency": "TEXT", "note": "TEXT", "bill_photo_ref": "TEXT",
            "status": "TEXT", "submitted_by": "TEXT", "approved_by": "TEXT",
            "created_at": "TEXT", "decided_at": "TEXT",
        },
        "json": [],
        "indexes": [
            {"cols": [("project_id", 1)], "unique": False},
            {"cols": [("status", 1)], "unique": False},
        ],
    },

    # <table name="checklists"><purpose>Factory/pack/load/unload/install/closure checklists with e-signature.</purpose></table>
    "checklists": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "project_id": "TEXT", "type": "TEXT", "status": "TEXT",
            "signed_by": "TEXT", "signature_ref": "TEXT",
            "created_at": "TEXT", "completed_at": "TEXT",
        },
        "json": [], "indexes": [{"cols": [("project_id", 1)], "unique": False}],
    },

    # <table name="checklist_items"><purpose>Individual checklist line items with photo evidence.</purpose></table>
    "checklist_items": {
        "pk": "id",
        "columns": {
            "id": "TEXT", "checklist_id": "TEXT", "label": "TEXT",
            "checked": "BOOLEAN", "photo_ref": "TEXT", "note": "TEXT",
            "checked_by": "TEXT", "checked_at": "TEXT",
        },
        "json": [], "indexes": [{"cols": [("checklist_id", 1)], "unique": False}],
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
            # <tamper-evidence> Hash chain: each entry's `hash` = SHA256 over its
            #   canonical content + the previous entry's `hash`. Deleting or editing
            #   any row breaks the chain (verify_audit_chain). AU-9 / A.8.15. </tamper-evidence>
            "prev_hash": "TEXT",
            "hash": "TEXT",
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

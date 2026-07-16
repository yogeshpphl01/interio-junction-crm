"""
<module name="permissions" layer="rbac">
  <purpose>
    Permission catalog + role -> permission resolution (Module 7). Built-in
    roles carry a fixed permission set; custom account categories created by the
    CEO/Admin carry their own explicit permission list (the "toggles"). Access
    checks read an in-memory cache (refreshed whenever roles change), so they
    are cheap and need no per-request DB hit.
  </purpose>
  <no-core-import>
    This module must NOT import core at load time (core imports has_permission),
    so the few DB-touching helpers take `db` as an argument and get_current_user
    is imported lazily inside require_permission.
  </no-core-import>
</module>
"""
from datetime import datetime, timezone
from fastapi import Depends, HTTPException


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# <catalog> (key, human label, group) — the toggles shown in the UI. </catalog>
PERMISSION_CATALOG = [
    ("leads.view_all",      "View all leads (not just own)",        "Leads"),
    ("leads.edit",          "Create / edit / move / close leads",   "Leads"),
    ("leads.import",        "Import lead spreadsheets",             "Leads"),
    ("leads.assign",        "Assign leads to team members",         "Leads"),
    ("measurements.manage", "Manage site measurements",             "Projects"),
    ("revisions.manage",    "Manage design revisions",              "Projects"),
    # <sod-payments> Money is split so recording a payment is NEVER the same act
    #   as confirming it (create-vs-record separation, NIST AC-5 / ISO A.5.3).
    #   `payments.manage` is retained ONLY as a legacy umbrella for any custom
    #   role that still holds it (it implies both record + confirm); no built-in
    #   role is granted it anymore. </sod-payments>
    ("payments.record",     "Record / enter payments",              "Projects"),
    ("payments.confirm",    "Confirm & verify payments (finance)",   "Projects"),
    ("payments.refund",     "Issue payment refunds (finance)",       "Projects"),
    ("payments.manage",     "Manage payments (legacy: record+confirm)", "Projects"),
    ("documents.upload",    "Upload documents",                     "Projects"),
    ("analytics.company",   "Company-wide analytics",               "Insights"),
    ("scoring.manage",      "Edit lead-scoring weights",            "Insights"),
    ("automations.manage",  "Manage automations",                   "Insights"),
    ("users.manage",        "Create / deactivate / reset accounts", "Administration"),
    ("users.delete",        "Permanently delete accounts",          "Administration"),
    ("roles.manage",        "Manage account categories",            "Administration"),
    ("audit.view",          "View the audit log",                   "Administration"),
    ("notifications.manage", "Manage notifications",                "Administration"),
    # <mobile-hierarchy> permission keys for the two-app ecosystem (docs/mobile-apps).
    #   Additive: they have no endpoints in the web CRM yet, so granting them is
    #   harmless there and establishes the RBAC model the mobile apps will use. </mobile-hierarchy>
    ("leads.upload_excel",  "Upload the ad-campaign Excel (Marketing Head)", "Leads"),
    ("leads.distribute",    "Distribute leads to Project Managers",  "Leads"),
    ("estimates.create",    "Create / submit estimates",             "Estimates"),
    ("estimates.approve",   "Approve estimates",                     "Estimates"),
    ("projects.coordinate", "Create project groups, add members, activate", "Projects"),
    ("production.manage",   "Cut list, Part IDs, QR, scans, QC, packing, dispatch", "Production"),
    ("installation.manage", "Site checklists, installation, completion", "Site"),
    ("tickets.manage",      "Raise / resolve site & production tickets", "Site"),
    ("expenses.submit",     "Submit site expense bills",             "Site"),
    ("expenses.approve",    "Approve site expenses",                 "Projects"),
    ("chat.access",         "Participate in chat",                   "Communication"),
    ("oversight.silent",    "Silent (invisible) project oversight",  "Administration"),
]
ALL_PERMISSIONS = [k for k, _, _ in PERMISSION_CATALOG]
_ALL = set(ALL_PERMISSIONS)

# <defaults>
#   Built-in role -> permission set. The web CRM's original access is preserved
#   (every key it granted is still granted); the mobile-hierarchy keys are layered
#   on so ONE backend powers both the web CRM and the two mobile apps. Superset
#   relationships are expressed by set-union so the matrix stays the source of
#   truth (Marketing Head ⊇ Project Manager, Production Engineer ⊇ Designer).
# </defaults>
_MANAGER_KEYS = {  # Project Manager — approves work and CONFIRMS money, but does not create estimates
    "leads.view_all", "leads.edit", "leads.import", "leads.assign", "analytics.company",
    "estimates.approve", "projects.coordinate", "expenses.approve", "payments.confirm",
    "tickets.manage", "chat.access",
}
_SALES_KEYS = {  # Sales Executive — creates the deal + RECORDS money, but can never CONFIRM it (SoD)
    "leads.edit", "leads.import", "measurements.manage", "revisions.manage",
    "payments.record", "documents.upload", "estimates.create", "chat.access",
}
_ACCOUNTS_KEYS = {  # Finance / Accounts — the money authority: record + confirm + refund + approve expenses
    "payments.record", "payments.confirm", "payments.refund", "expenses.approve",
    "analytics.company", "documents.upload", "chat.access",
}
_DESIGNER_KEYS = {"revisions.manage", "documents.upload", "chat.access"}
_SUPERVISOR_KEYS = {  # Site Manager
    "measurements.manage", "documents.upload", "installation.manage",
    "tickets.manage", "expenses.submit", "chat.access",
}
ROLE_DEFAULTS: dict[str, set] = {
    "ceo": set(_ALL),                              # everything (four-eyes still blocks self-approval)
    # <split-admin> The system administrator manages users/roles/automations but is
    #   separated from financial CONFIRMATION and the legacy money umbrella
    #   (NIST AC-5 duty separation). Admin can still record a payment operationally
    #   but a second party (Accounts / Manager / CEO) must confirm it. </split-admin>
    "admin": _ALL - {"users.delete", "payments.confirm", "payments.refund", "payments.manage"},
    # Marketing Head ⊇ Project Manager + campaign upload/distribute + silent oversight.
    "marketing_head": _MANAGER_KEYS | {"leads.upload_excel", "leads.distribute", "oversight.silent"},
    "manager": set(_MANAGER_KEYS),
    "sales": set(_SALES_KEYS),
    "accounts": set(_ACCOUNTS_KEYS),
    # Production Engineer ⊇ Designer + factory / cut-list / QR / production.
    "production_engineer": _DESIGNER_KEYS | {"production.manage", "tickets.manage"},
    "designer": set(_DESIGNER_KEYS),
    "supervisor": set(_SUPERVISOR_KEYS),
}
# Built-in label + colour (for seeding the roles table). Labels align with the
# mobile hierarchy (Project Manager / Site Manager) — code-authoritative for
# built-ins, so a redeploy re-syncs them (seed_roles).
ROLE_META = {
    "ceo": ("CEO", "#5C3A21"),
    "admin": ("Admin", "#C2683D"),
    "marketing_head": ("Marketing Head", "#7B4B94"),
    "manager": ("Project Manager", "#8A9A5B"),
    "sales": ("Sales Executive", "#8A5A3B"),
    "accounts": ("Finance / Accounts", "#4E6E58"),
    "production_engineer": ("Production Engineer", "#3B6E8F"),
    "designer": ("Designer", "#9C6644"),
    "supervisor": ("Site Manager", "#6B705C"),
}

# In-memory caches: role key -> permission set, and role key -> (label, colour).
# Both are rebuilt together whenever the roles table changes (set_role_cache).
_role_perms: dict[str, set] = dict(ROLE_DEFAULTS)
_role_meta: dict[str, tuple] = dict(ROLE_META)


def has_permission(user: dict, perm: str) -> bool:
    """True if the user's role grants `perm`. CEO always passes (super-admin)."""
    role = user.get("role")
    if role == "ceo":
        return True
    return perm in _role_perms.get(role, set())


def permissions_for(role: str) -> list[str]:
    """The full permission list for a role (used to enrich the user object so the
    frontend can show/hide features by permission)."""
    if role == "ceo":
        return list(ALL_PERMISSIONS)
    return sorted(_role_perms.get(role, set()))


def role_label(role: str) -> str:
    """Human label for a role key (built-in or custom). Falls back to the key."""
    return _role_meta.get(role, (str(role).title(), ""))[0]


def role_color(role: str) -> str:
    """Display colour for a role key. Falls back to a neutral tone."""
    return _role_meta.get(role, ("", "#8A817C"))[1]


def require_permission(perm: str):
    """FastAPI dependency that 403s unless the current user has `perm`."""
    from core import get_current_user  # lazy import to avoid a circular import

    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(user, perm):
            raise HTTPException(status_code=403, detail=f"Forbidden: missing permission '{perm}'")
        return user

    return dep


def has_any(user: dict, *perms: str) -> bool:
    """True if the user holds ANY of `perms` (CEO always passes)."""
    return any(has_permission(user, p) for p in perms)


def require_any_permission(*perms: str):
    """FastAPI dependency that 403s unless the user has AT LEAST ONE of `perms`.
    Used for the split money permissions where the legacy `payments.manage`
    umbrella still satisfies both `payments.record` and `payments.confirm`."""
    from core import get_current_user  # lazy import to avoid a circular import

    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if not has_any(user, *perms):
            raise HTTPException(status_code=403, detail=f"Forbidden: requires one of {', '.join(perms)}")
        return user

    return dep


def set_role_cache(roles: list[dict]) -> None:
    """Rebuild the in-memory caches (permissions + display meta) from role rows
    (skips soft-deleted)."""
    global _role_perms, _role_meta
    perms: dict[str, set] = {}
    meta: dict[str, tuple] = {}
    for r in roles:
        if r.get("is_deleted"):
            continue
        perms[r["key"]] = set(r.get("permissions") or [])
        meta[r["key"]] = (r.get("label") or str(r["key"]).title(), r.get("color") or "#8A817C")
    # Always keep the built-ins available even if the table read failed.
    for key, p in ROLE_DEFAULTS.items():
        perms.setdefault(key, set(p))
    for key, m in ROLE_META.items():
        meta.setdefault(key, m)
    _role_perms = perms
    _role_meta = meta


async def refresh_role_cache(db) -> None:
    roles = await db.roles.find({}, {"_id": 0}).to_list(1000)
    set_role_cache(roles)


async def seed_roles(db) -> None:
    """Insert missing built-in roles and keep existing SYSTEM roles in sync with
    code (permissions + label + colour are code-authoritative for built-ins, which
    is why the Module 7 UI shows them read-only). Custom categories are never
    touched. This lets a redeploy pick up newly-added permission keys/roles (e.g.
    the mobile-hierarchy additions). Then it loads the in-memory cache."""
    for key, perms in ROLE_DEFAULTS.items():
        label, color = ROLE_META.get(key, (key.title(), "#8A817C"))
        desired = sorted(perms)
        existing = await db.roles.find_one({"key": key})
        if not existing:
            await db.roles.insert_one({
                "key": key, "label": label, "color": color,
                "base_role": None, "permissions": desired,
                "is_system": True, "is_deleted": False,
                "created_by": None, "created_at": _now(),
            })
        elif existing.get("is_system"):
            patch = {}
            if set(existing.get("permissions") or []) != set(desired):
                patch["permissions"] = desired
            if existing.get("label") != label:
                patch["label"] = label
            if existing.get("color") != color:
                patch["color"] = color
            if existing.get("is_deleted"):
                patch["is_deleted"] = False  # a built-in must never stay soft-deleted
            if patch:
                await db.roles.update_one({"key": key}, {"$set": patch})
    await refresh_role_cache(db)

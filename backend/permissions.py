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
    ("payments.manage",     "Manage payments",                      "Projects"),
    ("documents.upload",    "Upload documents",                     "Projects"),
    ("analytics.company",   "Company-wide analytics",               "Insights"),
    ("scoring.manage",      "Edit lead-scoring weights",            "Insights"),
    ("automations.manage",  "Manage automations",                   "Insights"),
    ("users.manage",        "Create / deactivate / reset accounts", "Administration"),
    ("users.delete",        "Permanently delete accounts",          "Administration"),
    ("roles.manage",        "Manage account categories",            "Administration"),
    ("audit.view",          "View the audit log",                   "Administration"),
    ("notifications.manage", "Manage notifications",                "Administration"),
]
ALL_PERMISSIONS = [k for k, _, _ in PERMISSION_CATALOG]
_ALL = set(ALL_PERMISSIONS)

# <defaults> Built-in role -> permission set (reproduces today's access exactly). </defaults>
ROLE_DEFAULTS: dict[str, set] = {
    "ceo": set(_ALL),                              # everything
    "admin": _ALL - {"users.delete"},              # everything except hard-delete
    "manager": {"leads.view_all", "leads.edit", "leads.import", "leads.assign", "analytics.company"},
    "sales": {"leads.edit", "leads.import", "measurements.manage", "revisions.manage",
              "payments.manage", "documents.upload"},
    "designer": {"revisions.manage", "documents.upload"},
    "supervisor": {"measurements.manage", "documents.upload"},
}
# Built-in label + colour (for seeding the roles table).
ROLE_META = {
    "ceo": ("CEO", "#5C3A21"),
    "admin": ("Admin", "#C2683D"),
    "manager": ("Manager", "#8A9A5B"),
    "sales": ("Sales Executive", "#8A5A3B"),
    "designer": ("Designer", "#9C6644"),
    "supervisor": ("Site Supervisor", "#6B705C"),
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
    """Upsert the built-in roles into the roles table, then load the cache."""
    for key, perms in ROLE_DEFAULTS.items():
        if not await db.roles.find_one({"key": key}):
            label, color = ROLE_META.get(key, (key.title(), "#8A817C"))
            await db.roles.insert_one({
                "key": key, "label": label, "color": color,
                "base_role": None, "permissions": sorted(perms),
                "is_system": True, "is_deleted": False,
                "created_by": None, "created_at": _now(),
            })
    await refresh_role_cache(db)

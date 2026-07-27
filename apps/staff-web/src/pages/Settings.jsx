/*
  <page name="Settings" route="/settings" access="users.manage | roles.manage">
    <purpose>
      Workspace administration, two tabs:
        • Users (Module 1.5) — list accounts; create with a role + one-time password
          shown once; reset password; deactivate / reactivate; CEO-only delete.
        • Account Categories (Module 7) — CEO/Admin create, edit and delete custom
          account categories (roles) with explicit permission toggles. Built-in
          categories are read-only; a deleted custom category is soft-deleted and
          its record is retained in the database.
    </purpose>
    <gating>Mutating controls are shown only when the signed-in user holds the
    matching permission; the backend independently enforces the same rules.</gating>
  </page>
*/
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ROLE_LABEL, ROLE_COLOR } from "@/lib/constants";
import { initials, fmtDate } from "@/lib/format";
import { toast, Toaster } from "sonner";
import { Plus, KeyRound, UserX, UserCheck, Copy, Check, Trash2, Pencil, Lock, ShieldCheck, Users as UsersIcon } from "lucide-react";

// Preset swatches for category colours (the app's warm clay/sage palette).
const CATEGORY_PALETTE = ["#5C3A21", "#C2683D", "#8A9A5B", "#8A5A3B", "#9C6644", "#6B705C", "#A95A3F", "#4A5D23", "#6B4226", "#7D8471"];

export default function Settings() {
  const { user: me } = useAuth();
  const isCeo = me?.role === "ceo";
  const myPerms = me?.permissions || [];
  const canManageUsers = isCeo || myPerms.includes("users.manage");
  const canManageRoles = isCeo || myPerms.includes("roles.manage");

  const [tab, setTab] = useState("users");
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [credential, setCredential] = useState(null); // {email, password} shown once

  // Map role key -> {label, color, ...} from the live roles table (covers custom
  // categories); fall back to the built-in constants if a key is missing.
  const roleMap = useMemo(() => Object.fromEntries(roles.map((r) => [r.key, r])), [roles]);
  const labelFor = (key) => roleMap[key]?.label || ROLE_LABEL[key] || key;
  const colorFor = (key) => roleMap[key]?.color || ROLE_COLOR[key] || "#8A817C";

  const loadUsers = async () => setUsers((await api.get("/users")).data);
  const loadRoles = async () => setRoles((await api.get("/roles")).data);

  const load = async () => {
    setLoading(true);
    try {
      await Promise.all([loadUsers(), loadRoles()]);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);
  // If the user can only manage categories, open that tab by default.
  useEffect(() => { if (!canManageUsers && canManageRoles) setTab("roles"); }, [canManageUsers, canManageRoles]);

  const resetPwd = async (u) => {
    try {
      const { data } = await api.post(`/users/${u.id}/reset-password`);
      setCredential({ email: u.email, password: data.generated_password });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reset failed");
    }
  };

  const toggleActive = async (u) => {
    try {
      await api.post(`/users/${u.id}/${u.is_active ? "deactivate" : "activate"}`);
      toast.success(u.is_active ? "Account deactivated" : "Account reactivated");
      loadUsers();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  // Hard delete — CEO only; the backend also forbids deleting a CEO account.
  const hardDelete = async (u) => {
    if (!window.confirm(`Permanently delete ${u.full_name} (${u.email})?\nThis cannot be undone. Their past actions stay in the audit log.`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      toast.success("Account deleted");
      loadUsers();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const TABS = [
    { key: "users", label: "Users", icon: UsersIcon, show: true },
    { key: "roles", label: "Account Categories", icon: ShieldCheck, show: canManageRoles },
  ].filter((t) => t.show);

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="flex items-end justify-between mb-5">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Settings</h2>
          <p className="text-ink-muted text-sm mt-2">Workspace users &amp; account categories.</p>
        </div>
        {tab === "users" && canManageUsers && (
          <button onClick={() => setCreating(true)} className="text-xs bg-clay text-white rounded-md px-3 py-2 inline-flex items-center gap-1" data-testid="new-user-btn">
            <Plus className="w-3.5 h-3.5" /> New user
          </button>
        )}
      </div>

      {/* Tab strip — only shows the categories tab to users who can manage roles. */}
      {TABS.length > 1 && (
        <div className="flex items-center gap-1 mb-5 border-b border-edge">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button key={t.key} onClick={() => setTab(t.key)} data-testid={`settings-tab-${t.key}`}
                className={`inline-flex items-center gap-2 px-3 py-2 text-sm -mb-px border-b-2 transition-colors ${active ? "border-clay text-ink" : "border-transparent text-ink-soft hover:text-ink"}`}>
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>
      )}

      {tab === "users" && (
        <UsersTable
          users={users} loading={loading} me={me} isCeo={isCeo} canManageUsers={canManageUsers}
          labelFor={labelFor} colorFor={colorFor}
          onReset={resetPwd} onToggle={toggleActive} onDelete={hardDelete}
        />
      )}

      {tab === "roles" && canManageRoles && (
        <RolesPanel roles={roles} loading={loading} isCeo={isCeo} users={users} onChanged={loadRoles} />
      )}

      {creating && (
        <NewUserModal
          roles={roles} isCeo={isCeo}
          onClose={() => setCreating(false)}
          onCreated={(data) => {
            setCreating(false);
            loadUsers();
            if (data?.generated_password) setCredential({ email: data.email, password: data.generated_password });
          }}
        />
      )}

      {credential && <CredentialModal cred={credential} onClose={() => setCredential(null)} />}
    </div>
  );
}

/* <component name="UsersTable">Account list + per-row admin actions.</component> */
function UsersTable({ users, loading, me, isCeo, canManageUsers, labelFor, colorFor, onReset, onToggle, onDelete }) {
  return (
    <div className="bg-bone-paper border border-edge rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-bone-subtle text-ink-soft">
          <tr className="text-left">
            <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">User</th>
            <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Category</th>
            <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Phone</th>
            <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Created</th>
            <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Status</th>
            <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={6} className="text-center py-10 text-ink-muted">Loading…</td></tr>}
          {users.map((u) => (
            <tr key={u.id} className="border-t border-edge hover:bg-bone" data-testid={`user-row-${u.email}`}>
              <td className="px-4 py-3 flex items-center gap-3">
                <div className="w-8 h-8 rounded-md text-white text-xs font-semibold flex items-center justify-center" style={{ background: colorFor(u.role) }}>
                  {initials(u.full_name)}
                </div>
                <div>
                  <div className="text-ink">{u.full_name}</div>
                  <div className="text-[11px] text-ink-muted">{u.email}</div>
                </div>
              </td>
              <td className="px-4 py-3">
                <span className="text-[11px] px-2 py-0.5 rounded-full border" style={{ background: `${colorFor(u.role)}1A`, color: colorFor(u.role), borderColor: `${colorFor(u.role)}33` }}>
                  {labelFor(u.role)}
                </span>
              </td>
              <td className="px-4 py-3 text-ink-soft text-xs">{u.phone || "—"}</td>
              <td className="px-4 py-3 text-ink-muted text-xs">{fmtDate(u.created_at)}</td>
              <td className="px-4 py-3">
                <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${u.is_active ? "text-stage-2 bg-stage-2/20" : "text-ink-muted bg-bone-subtle"}`}>
                  {u.is_active ? "Active" : "Disabled"}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-1">
                  {canManageUsers && (u.role !== "ceo" || isCeo) && (
                    <button onClick={() => onReset(u)} title="Reset password" data-testid={`reset-pwd-${u.email}`}
                      className="p-1.5 rounded hover:bg-bone-subtle text-ink-soft hover:text-clay">
                      <KeyRound className="w-4 h-4" />
                    </button>
                  )}
                  {canManageUsers && u.role !== "ceo" && (
                    <button onClick={() => onToggle(u)} title={u.is_active ? "Deactivate" : "Reactivate"} data-testid={`toggle-active-${u.email}`}
                      className="p-1.5 rounded hover:bg-bone-subtle text-ink-soft hover:text-clay">
                      {u.is_active ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
                    </button>
                  )}
                  {isCeo && u.role !== "ceo" && (
                    <button onClick={() => onDelete(u)} title="Delete permanently (CEO)" data-testid={`delete-${u.email}`}
                      className="p-1.5 rounded hover:bg-clay/10 text-ink-soft hover:text-clay-deep">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                  {u.role === "ceo" && (
                    <span className="text-[10px] uppercase tracking-wide text-ink-muted italic px-1">protected</span>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* <component name="RolesPanel">
     Module 7 — the grid of account categories. Built-in categories are read-only
     (a lock icon); custom categories can be edited or deleted. Deleting is blocked
     by the backend while any account still uses the category.
   </component> */
function RolesPanel({ roles, loading, isCeo, users, onChanged }) {
  const [catalog, setCatalog] = useState([]); // [{key,label,group}]
  const [editing, setEditing] = useState(null); // role object or {} for "new"

  useEffect(() => {
    api.get("/permissions").then(({ data }) => setCatalog(data.permissions || [])).catch(() => {});
  }, []);

  const countFor = (key) => users.filter((u) => u.role === key).length;

  const del = async (r) => {
    if (!window.confirm(`Delete the “${r.label}” category?\nThe record is kept in the database; accounts must be reassigned first.`)) return;
    try {
      await api.delete(`/roles/${r.key}`);
      toast.success("Category deleted");
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-ink-soft text-sm max-w-2xl">
          Account categories define what each kind of user can do. Toggle permissions per category;
          built-in categories are locked. Deleted custom categories are retained in the database for the record.
        </p>
        <button onClick={() => setEditing({})} data-testid="new-role-btn"
          className="shrink-0 text-xs bg-clay text-white rounded-md px-3 py-2 inline-flex items-center gap-1">
          <Plus className="w-3.5 h-3.5" /> New category
        </button>
      </div>

      {loading && <div className="text-center py-10 text-ink-muted">Loading…</div>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {roles.map((r) => {
          const inUse = countFor(r.key);
          return (
            <div key={r.key} className="bg-bone-paper border border-edge rounded-md p-4 flex flex-col" data-testid={`role-card-${r.key}`}>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ background: r.color }} />
                <span className="font-medium text-ink truncate">{r.label}</span>
                {r.is_system
                  ? <span className="ml-auto inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-ink-muted"><Lock className="w-3 h-3" /> Built-in</span>
                  : <span className="ml-auto text-[10px] uppercase tracking-wide text-clay">Custom</span>}
              </div>
              <div className="mt-2 text-[11px] text-ink-muted">
                {r.key === "ceo" ? "All permissions" : `${(r.permissions || []).length} permission${(r.permissions || []).length === 1 ? "" : "s"}`}
                <span className="mx-1.5">·</span>
                {inUse} account{inUse === 1 ? "" : "s"}
              </div>
              <div className="mt-3 pt-3 border-t border-edge flex items-center justify-end gap-1">
                {r.is_system ? (
                  <span className="text-[10px] uppercase tracking-wide text-ink-muted italic">read-only</span>
                ) : (
                  <>
                    <button onClick={() => setEditing(r)} title="Edit category" data-testid={`edit-role-${r.key}`}
                      className="p-1.5 rounded hover:bg-bone-subtle text-ink-soft hover:text-clay">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => del(r)} title="Delete category" data-testid={`delete-role-${r.key}`}
                      className="p-1.5 rounded hover:bg-clay/10 text-ink-soft hover:text-clay-deep">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {editing && (
        <RoleModal role={editing.key ? editing : null} catalog={catalog}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); onChanged(); }} />
      )}
    </div>
  );
}

/* <component name="RoleModal">Create / edit a custom category with grouped permission toggles.</component> */
function RoleModal({ role, catalog, onClose, onSaved }) {
  const isEdit = !!role;
  const [label, setLabel] = useState(role?.label || "");
  const [color, setColor] = useState(role?.color || CATEGORY_PALETTE[0]);
  const [perms, setPerms] = useState(() => new Set(role?.permissions || []));
  const [busy, setBusy] = useState(false);

  // Group catalog entries by their group, preserving catalog order.
  const groups = useMemo(() => {
    const out = [];
    for (const p of catalog) {
      let g = out.find((x) => x.name === p.group);
      if (!g) { g = { name: p.group, items: [] }; out.push(g); }
      g.items.push(p);
    }
    return out;
  }, [catalog]);

  const toggle = (key) => setPerms((prev) => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });

  const submit = async (e) => {
    e.preventDefault();
    if (!label.trim()) { toast.error("Category name is required"); return; }
    setBusy(true);
    try {
      const payload = { label: label.trim(), color, permissions: [...perms] };
      if (isEdit) await api.patch(`/roles/${role.key}`, payload);
      else await api.post("/roles", payload);
      toast.success(isEdit ? "Category updated" : "Category created");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-lg max-h-[88vh] flex flex-col" data-testid="role-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between items-center">
          <h3 className="font-serif text-xl text-ink">{isEdit ? "Edit category" : "New account category"}</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none">×</button>
        </div>
        <form onSubmit={submit} className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-4">
          <FieldS label="Category name">
            <input data-testid="role-label" required value={label} onChange={(e) => setLabel(e.target.value)} className={cls} placeholder="e.g. Telecaller, Project Manager" />
          </FieldS>
          <FieldS label="Colour">
            <div className="flex flex-wrap gap-2 mt-1">
              {CATEGORY_PALETTE.map((c) => (
                <button type="button" key={c} onClick={() => setColor(c)} aria-label={c}
                  className={`w-7 h-7 rounded-full border-2 transition ${color === c ? "border-ink scale-110" : "border-transparent"}`}
                  style={{ background: c }} />
              ))}
            </div>
          </FieldS>
          <div>
            <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">Permissions</span>
            <div className="mt-2 space-y-4">
              {groups.map((g) => (
                <div key={g.name}>
                  <div className="text-[11px] font-semibold text-ink-muted uppercase tracking-wide mb-1.5">{g.name}</div>
                  <div className="space-y-1.5">
                    {g.items.map((p) => (
                      <label key={p.key} className="flex items-center gap-2.5 text-sm text-ink cursor-pointer" data-testid={`perm-${p.key}`}>
                        <input type="checkbox" checked={perms.has(p.key)} onChange={() => toggle(p.key)}
                          className="w-4 h-4 rounded border-edge text-clay focus:ring-clay" />
                        <span>{p.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              {groups.length === 0 && <div className="text-ink-muted text-sm">Loading permissions…</div>}
            </div>
          </div>
        </form>
        <div className="px-5 py-4 border-t border-edge flex justify-between items-center">
          <span className="text-[11px] text-ink-muted">{perms.size} permission{perms.size === 1 ? "" : "s"} selected</span>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
            <button data-testid="submit-role" disabled={busy} onClick={submit} className="bg-clay text-white px-3 py-1.5 text-sm rounded disabled:opacity-50">
              {busy ? "Saving…" : isEdit ? "Save changes" : "Create category"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* <component name="CredentialModal">Shows a generated password ONCE for the admin to copy + share.</component> */
function CredentialModal({ cred, onClose }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(cred.password); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  };
  return (
    <div className="fixed inset-0 z-[60] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-md" data-testid="credential-modal">
        <div className="px-5 py-4 border-b border-edge">
          <h3 className="font-serif text-xl text-ink">One-time password</h3>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-sm text-ink-soft">Share this with <span className="font-medium text-ink">{cred.email}</span>. It won't be shown again.</p>
          <div className="flex items-center justify-between gap-2 bg-bone-subtle border border-edge rounded-md px-3 py-2.5">
            <code className="font-mono text-lg text-ink tracking-wide" data-testid="generated-password">{cred.password}</code>
            <button onClick={copy} className="p-1.5 rounded hover:bg-bone text-ink-soft hover:text-clay" title="Copy">
              {copied ? <Check className="w-4 h-4 text-[#4A5D23]" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <div className="flex justify-end pt-1">
            <button onClick={onClose} className="bg-clay text-white px-4 py-2 text-sm rounded-md">Done</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function NewUserModal({ roles, isCeo, onClose, onCreated }) {
  // Categories the creator may assign: all live ones, minus CEO unless a CEO is creating.
  const assignable = roles.filter((r) => r.key !== "ceo" || isCeo);
  const defaultRole = assignable.find((r) => r.key === "sales")?.key || assignable[0]?.key || "sales";
  const [form, setForm] = useState({ email: "", full_name: "", role: defaultRole, phone: "", password: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      // Omit password entirely when blank so the backend generates one.
      const payload = { ...form };
      if (!payload.password) delete payload.password;
      const { data } = await api.post("/users", payload);
      toast.success("User created");
      onCreated(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-md">
        <div className="px-5 py-4 border-b border-edge flex justify-between">
          <h3 className="font-serif text-xl text-ink">New user</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none">×</button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-3">
          <FieldS label="Full name"><input data-testid="user-name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className={cls} /></FieldS>
          <FieldS label="Email"><input data-testid="user-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={cls} /></FieldS>
          <FieldS label="Account category">
            <select data-testid="user-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className={cls}>
              {assignable.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
            </select>
          </FieldS>
          <FieldS label="Phone"><input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className={cls} /></FieldS>
          <FieldS label="Password (leave blank to auto-generate)"><input data-testid="user-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className={cls} placeholder="auto-generate a strong password" /></FieldS>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
            <button data-testid="submit-new-user" disabled={busy} type="submit" className="bg-clay text-white px-3 py-1.5 text-sm rounded disabled:opacity-50">{busy ? "Saving…" : "Create"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function FieldS({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
const cls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none";

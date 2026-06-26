/*
  <page name="Settings" route="/settings" access="admin">
    <purpose>
      Account management (Module 1.5). List users; create accounts with a role
      (incl. Manager) and an auto-generated one-time password shown once;
      reset a user's password; deactivate / reactivate accounts.
    </purpose>
  </page>
*/
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ROLE_LABEL, ROLE_COLOR } from "@/lib/constants";
import { initials, fmtDate } from "@/lib/format";
import { toast, Toaster } from "sonner";
import { Plus, KeyRound, UserX, UserCheck, Copy, Check, Trash2 } from "lucide-react";

export default function Settings() {
  const { user: me } = useAuth();
  const isCeo = me?.role === "ceo";
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [credential, setCredential] = useState(null); // {email, password} shown once

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/users");
      setUsers(data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

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
      load();
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
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="flex items-end justify-between mb-6">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Settings</h2>
          <p className="text-ink-muted text-sm mt-2">Workspace users &amp; roles.</p>
        </div>
        <button onClick={() => setCreating(true)} className="text-xs bg-clay text-white rounded-md px-3 py-2 inline-flex items-center gap-1" data-testid="new-user-btn">
          <Plus className="w-3.5 h-3.5" /> New user
        </button>
      </div>

      <div className="bg-bone-paper border border-edge rounded-md overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-bone-subtle text-ink-soft">
            <tr className="text-left">
              <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">User</th>
              <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Role</th>
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
                  <div className="w-8 h-8 rounded-md text-white text-xs font-semibold flex items-center justify-center" style={{ background: ROLE_COLOR[u.role] }}>
                    {initials(u.full_name)}
                  </div>
                  <div>
                    <div className="text-ink">{u.full_name}</div>
                    <div className="text-[11px] text-ink-muted">{u.email}</div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-[11px] px-2 py-0.5 rounded-full border" style={{ background: `${ROLE_COLOR[u.role]}1A`, color: ROLE_COLOR[u.role], borderColor: `${ROLE_COLOR[u.role]}33` }}>
                    {ROLE_LABEL[u.role] || u.role}
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
                    {(u.role !== "ceo" || isCeo) && (
                      <button onClick={() => resetPwd(u)} title="Reset password" data-testid={`reset-pwd-${u.email}`}
                        className="p-1.5 rounded hover:bg-bone-subtle text-ink-soft hover:text-clay">
                        <KeyRound className="w-4 h-4" />
                      </button>
                    )}
                    {u.role !== "ceo" && (
                      <button onClick={() => toggleActive(u)} title={u.is_active ? "Deactivate" : "Reactivate"} data-testid={`toggle-active-${u.email}`}
                        className="p-1.5 rounded hover:bg-bone-subtle text-ink-soft hover:text-clay">
                        {u.is_active ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
                      </button>
                    )}
                    {isCeo && u.role !== "ceo" && (
                      <button onClick={() => hardDelete(u)} title="Delete permanently (CEO)" data-testid={`delete-${u.email}`}
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

      {creating && (
        <NewUserModal
          onClose={() => setCreating(false)}
          onCreated={(data) => {
            setCreating(false);
            load();
            if (data?.generated_password) setCredential({ email: data.email, password: data.generated_password });
          }}
        />
      )}

      {credential && <CredentialModal cred={credential} onClose={() => setCredential(null)} />}
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

function NewUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ email: "", full_name: "", role: "sales", phone: "", password: "" });
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
          <FieldS label="Role">
            <select data-testid="user-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className={cls}>
              {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
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

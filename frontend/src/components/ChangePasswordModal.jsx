/*
  <component name="ChangePasswordModal" layer="frontend">
    <purpose>
      Module 1.4 — lets ANY signed-in user change their own password. Verifies
      the current password server-side (POST /auth/change-password).
    </purpose>
  </component>
*/
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ChangePasswordModal({ onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (next.length < 8) return toast.error("New password must be at least 8 characters");
    if (next !== confirm) return toast.error("New passwords do not match");
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current, new: next });
      toast.success("Password changed");
      onClose();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not change password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-sm" data-testid="change-password-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between">
          <h3 className="font-serif text-xl text-ink">Change password</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none">×</button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-3">
          <Field label="Current password">
            <input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} className={cls} data-testid="cp-current" />
          </Field>
          <Field label="New password">
            <input type="password" required value={next} onChange={(e) => setNext(e.target.value)} className={cls} data-testid="cp-new" placeholder="at least 8 characters" />
          </Field>
          <Field label="Confirm new password">
            <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={cls} data-testid="cp-confirm" />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
            <button type="submit" disabled={busy} data-testid="cp-submit" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
              {busy ? "Saving…" : "Update password"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
const cls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none";

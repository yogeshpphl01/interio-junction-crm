/*
  <component name="EditProfileModal" layer="frontend">
    <purpose>
      Module 1.4 — any signed-in user edits their own personal details
      (name, phone) via PATCH /auth/profile. Every change is recorded in the
      audit log on the server (before -> after).
    </purpose>
  </component>
*/
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function EditProfileModal({ onClose }) {
  const { user, refresh } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.patch("/auth/profile", { full_name: fullName, phone });
      await refresh();           // update the name/phone shown in the shell
      toast.success("Profile updated");
      onClose();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not update profile");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-sm" data-testid="edit-profile-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between">
          <h3 className="font-serif text-xl text-ink">Edit profile</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none">×</button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-3">
          <Field label="Email (login — not editable here)">
            <input value={user?.email || ""} disabled className={cls + " opacity-60 cursor-not-allowed"} />
          </Field>
          <Field label="Full name">
            <input required value={fullName} onChange={(e) => setFullName(e.target.value)} className={cls} data-testid="profile-name" />
          </Field>
          <Field label="Phone / mobile">
            <input value={phone} onChange={(e) => setPhone(e.target.value)} className={cls} data-testid="profile-phone" placeholder="+91 …" />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
            <button type="submit" disabled={busy} data-testid="profile-submit" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
              {busy ? "Saving…" : "Save changes"}
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

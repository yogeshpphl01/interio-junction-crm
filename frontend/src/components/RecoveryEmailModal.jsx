/*
  <component name="RecoveryEmailModal" layer="frontend">
    <purpose>
      First-login capture (Module 2). Prompts a signed-in user who has no recovery
      email on file to add a personal inbox, which is where password-reset codes
      are sent. Saved via PATCH /auth/profile (audit-logged like any profile edit).
      Skippable for the session, but reappears next login until set, so most users
      end up with a working self-service reset path.
    </purpose>
  </component>
*/
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { LifeBuoy } from "lucide-react";

export default function RecoveryEmailModal({ onClose, onSkip }) {
  const { user, refresh } = useAuth();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    const v = value.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) { setError("Enter a valid email address"); return; }
    if (v.toLowerCase() === (user?.email || "").toLowerCase()) {
      setError("Use a personal email different from your login email");
      return;
    }
    setError(""); setBusy(true);
    try {
      await api.patch("/auth/profile", { recovery_email: v });
      await refresh();        // user.recovery_email is now set -> modal closes
      toast.success("Recovery email saved");
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not save. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[65] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-bone-paper border border-edge rounded-md w-full max-w-sm" data-testid="recovery-email-modal">
        <div className="px-5 py-4 border-b border-edge flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md bg-clay/10 text-clay flex items-center justify-center">
            <LifeBuoy className="w-4 h-4" />
          </div>
          <h3 className="font-serif text-xl text-ink">Add a recovery email</h3>
        </div>
        <form onSubmit={submit} className="p-5 space-y-3">
          <p className="text-sm text-ink-soft">
            Set a personal email so you can reset your password yourself if you ever forget it.
            Reset codes are sent here — keep it different from your shared login email.
          </p>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">Personal email</span>
            <input
              type="email" value={value} onChange={(e) => setValue(e.target.value)} autoFocus
              data-testid="recovery-email-input" placeholder="you@gmail.com"
              className="mt-1 w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none"
            />
          </label>
          {error && <div data-testid="recovery-email-error" className="text-sm text-clay-deep bg-clay/10 border border-clay/30 rounded-md px-3 py-2">{error}</div>}
          <div className="flex items-center justify-between pt-1">
            <button type="button" onClick={onSkip} data-testid="recovery-skip-btn" className="text-xs text-ink-soft hover:text-ink">Skip for now</button>
            <button type="submit" disabled={busy} data-testid="recovery-save-btn" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

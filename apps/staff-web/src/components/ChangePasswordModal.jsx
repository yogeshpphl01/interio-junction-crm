/*
  <component name="ChangePasswordModal" layer="frontend">
    <purpose>
      Module 1.4 — lets ANY signed-in user change their own password. Verifies
      the current password server-side (POST /auth/change-password).

      item 11 (DPDP hardening): three wrong current-password tries lock the change
      path (HTTP 423, detail.reset_required). We then switch to a reset flow that
      sends a one-time code to the account's recovery email AND phone
      (/auth/change-password/challenge) and completes with
      /auth/change-password/verify. A "Forgot your current password?" link lets the
      user start that same reset flow proactively.
    </purpose>
  </component>
*/
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ChangePasswordModal({ onClose }) {
  // "change" = normal current+new; "reset" = OTP (email+phone) after lockout/forgot.
  const [mode, setMode] = useState("change");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [otp, setOtp] = useState("");
  const [sentTo, setSentTo] = useState({ email: "", phone: "" });
  const [busy, setBusy] = useState(false);

  // Ask the server to send a code to the recovery email + phone, then show reset UI.
  const startReset = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/change-password/challenge");
      setSentTo({ email: data?.email || "", phone: data?.phone || "" });
      setMode("reset");
      toast.success(data?.message || "We sent you a one-time code");
    } catch (err) {
      toast.error(err?.response?.data?.detail?.message || err?.response?.data?.detail || "Could not send a code");
    } finally {
      setBusy(false);
    }
  };

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
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      // Locked after too many wrong tries → move to the email+phone OTP reset.
      if (status === 423 || detail?.reset_required) {
        toast.error(detail?.message || "Too many attempts — resetting via a one-time code");
        await startReset();
      } else {
        toast.error(typeof detail === "string" ? detail : detail?.message || "Could not change password");
      }
    } finally {
      setBusy(false);
    }
  };

  const submitReset = async (e) => {
    e.preventDefault();
    if (!otp.trim()) return toast.error("Enter the code we sent you");
    if (next.length < 8) return toast.error("New password must be at least 8 characters");
    if (next !== confirm) return toast.error("New passwords do not match");
    setBusy(true);
    try {
      await api.post("/auth/change-password/verify", { otp: otp.trim(), new_password: next });
      toast.success("Password updated");
      onClose();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Invalid or expired code");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-sm" data-testid="change-password-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between">
          <h3 className="font-serif text-xl text-ink">{mode === "reset" ? "Reset password" : "Change password"}</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none">×</button>
        </div>

        {mode === "change" ? (
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
            <div className="flex items-center justify-between pt-1">
              <button type="button" onClick={startReset} disabled={busy} data-testid="cp-forgot" className="text-xs text-clay hover:underline disabled:opacity-50">
                Forgot your current password?
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
                <button type="submit" disabled={busy} data-testid="cp-submit" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
                  {busy ? "Saving…" : "Update password"}
                </button>
              </div>
            </div>
          </form>
        ) : (
          <form onSubmit={submitReset} className="p-5 space-y-3" data-testid="cp-reset-form">
            <p className="text-xs text-ink-soft leading-relaxed">
              We sent a one-time code to
              {sentTo.email ? <> your recovery email <b className="text-ink">{sentTo.email}</b></> : null}
              {sentTo.email && sentTo.phone ? " and" : null}
              {sentTo.phone ? <> your phone <b className="text-ink">{sentTo.phone}</b></> : null}. Enter it below with your new password.
            </p>
            <Field label="One-time code">
              <input inputMode="numeric" required value={otp} onChange={(e) => setOtp(e.target.value)} className={cls} data-testid="cp-otp" placeholder="4-digit code" />
            </Field>
            <Field label="New password">
              <input type="password" required value={next} onChange={(e) => setNext(e.target.value)} className={cls} data-testid="cp-reset-new" placeholder="at least 8 characters" />
            </Field>
            <Field label="Confirm new password">
              <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={cls} data-testid="cp-reset-confirm" />
            </Field>
            <div className="flex items-center justify-between pt-1">
              <button type="button" onClick={startReset} disabled={busy} className="text-xs text-clay hover:underline disabled:opacity-50">
                Resend code
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
                <button type="submit" disabled={busy} data-testid="cp-reset-submit" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
                  {busy ? "Saving…" : "Reset password"}
                </button>
              </div>
            </div>
          </form>
        )}
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

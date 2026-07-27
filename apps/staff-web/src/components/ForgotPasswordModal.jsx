/*
  <component name="ForgotPasswordModal" layer="frontend">
    <purpose>
      Self-service password reset (Module 2). Two steps:
        1. Enter the account's login email -> POST /auth/forgot-password sends a
           4-digit code to the user's recovery email.
        2. Enter the code + a new password -> POST /auth/reset-password.
      The backend returns a generic message in step 1 (it never reveals whether an
      account exists), so the UI always advances to step 2 and lets the user enter
      the code they received. Delivery is email today and pluggable to SMS later.
    </purpose>
  </component>
*/
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const RESEND_COOLDOWN = 60;

export default function ForgotPasswordModal({ onClose, initialEmail = "" }) {
  const [step, setStep] = useState("request"); // "request" | "verify"
  const [email, setEmail] = useState(initialEmail);
  const [otp, setOtp] = useState("");
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(0);

  // Tick down the resend cooldown.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => (c <= 1 ? 0 : c - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const requestCode = async (e) => {
    e?.preventDefault();
    if (!email.trim()) { setError("Enter your account email"); return; }
    setError(""); setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email: email.trim() });
      setStep("verify");
      setCooldown(RESEND_COOLDOWN);
      toast.success("If the account has a recovery email, a code is on its way.");
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not send a code. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (cooldown > 0 || busy) return;
    await requestCode();
  };

  const submitReset = async (e) => {
    e.preventDefault();
    if (!/^\d{4}$/.test(otp.trim())) { setError("Enter the 4-digit code from your email"); return; }
    if (pwd.length < 8) { setError("New password must be at least 8 characters"); return; }
    if (pwd !== confirm) { setError("Passwords do not match"); return; }
    setError(""); setBusy(true);
    try {
      await api.post("/auth/reset-password", { email: email.trim(), otp: otp.trim(), new_password: pwd });
      toast.success("Password updated — sign in with your new password.");
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || "Invalid or expired code.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-sm" data-testid="forgot-password-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between items-center">
          <h3 className="font-serif text-xl text-ink">Reset password</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none" aria-label="Close">×</button>
        </div>

        {step === "request" ? (
          <form onSubmit={requestCode} className="p-5 space-y-3">
            <p className="text-sm text-ink-soft">Enter your account email. We'll send a one-time code to the recovery email on file.</p>
            <Field label="Account email">
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={cls}
                data-testid="forgot-email-input" placeholder="you@interiojunction.com" autoFocus />
            </Field>
            {error && <ErrorNote>{error}</ErrorNote>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
              <button type="submit" disabled={busy} data-testid="forgot-send-btn" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
                {busy ? "Sending…" : "Send code"}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={submitReset} className="p-5 space-y-3">
            <p className="text-sm text-ink-soft">Enter the 4-digit code sent to your recovery email, then choose a new password.</p>
            <Field label="4-digit code">
              <input inputMode="numeric" maxLength={4} required value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                className={cls + " tracking-[0.5em] text-center font-mono text-lg"} data-testid="reset-otp-input" placeholder="••••" autoFocus />
            </Field>
            <Field label="New password">
              <input type="password" required value={pwd} onChange={(e) => setPwd(e.target.value)} className={cls}
                data-testid="reset-new-password" placeholder="At least 8 characters" />
            </Field>
            <Field label="Confirm new password">
              <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={cls}
                data-testid="reset-confirm-password" />
            </Field>
            {error && <ErrorNote>{error}</ErrorNote>}
            <div className="flex items-center justify-between pt-1">
              <button type="button" onClick={resend} disabled={cooldown > 0 || busy} data-testid="reset-resend-btn"
                className="text-xs text-clay hover:text-clay-deep disabled:text-ink-muted disabled:cursor-not-allowed">
                {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={() => { setStep("request"); setError(""); }} className="px-3 py-1.5 text-sm text-ink-soft">Back</button>
                <button type="submit" disabled={busy} data-testid="reset-submit-btn" className="bg-clay text-white px-3 py-1.5 text-sm rounded-md disabled:opacity-50">
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
function ErrorNote({ children }) {
  return <div data-testid="forgot-error" className="text-sm text-clay-deep bg-clay/10 border border-clay/30 rounded-md px-3 py-2">{children}</div>;
}
const cls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none";

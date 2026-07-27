/*
  <component name="SecurityModal" layer="frontend">
    <purpose>
      Per-user account security (any signed-in staff member). Manages two-factor
      authentication (TOTP, P1-6): enrol -> scan/enter secret -> confirm a code ->
      save one-time backup codes; and disable (requires a current code). The same
      TOTP also satisfies step-up prompts on sensitive actions.
    </purpose>
    <backend>
      GET  /auth/mfa/status     {enrolled, backup_codes_remaining}
      POST /auth/mfa/enroll     -> {secret, otpauth_uri}
      POST /auth/mfa/activate   {code} -> {backup_codes}
      POST /auth/mfa/disable    {code}
    </backend>
  </component>
*/
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ShieldCheck, ShieldAlert, Copy, Check, KeyRound, Fingerprint, Plus, Trash2 } from "lucide-react";
import { registerPasskey, listPasskeys, deletePasskey, passkeySupported, isPasskeyCancel } from "@/lib/webauthn";

const cls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none";

export default function SecurityModal({ onClose }) {
  const { refresh } = useAuth();
  const [status, setStatus] = useState(null);          // {enrolled, backup_codes_remaining}
  const [phase, setPhase] = useState("view");          // view | enrolling | backup | disabling
  const [enroll, setEnroll] = useState(null);          // {secret, otpauth_uri}
  const [code, setCode] = useState("");
  const [backupCodes, setBackupCodes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [passkeys, setPasskeys] = useState([]);
  const [pkBusy, setPkBusy] = useState(false);

  const loadStatus = async () => {
    try { setStatus((await api.get("/auth/mfa/status")).data); }
    catch { setStatus({ enrolled: false }); }
  };
  const loadPasskeys = async () => {
    if (!passkeySupported()) return;
    try { setPasskeys(await listPasskeys()); } catch { /* ignore */ }
  };
  useEffect(() => { loadStatus(); loadPasskeys(); }, []);

  const addPasskey = async () => {
    setPkBusy(true);
    try {
      await registerPasskey("Passkey");
      toast.success("Passkey added");
      await loadPasskeys();
    } catch (e) {
      if (!isPasskeyCancel(e)) toast.error(e?.response?.data?.detail || "Could not add passkey");
    } finally { setPkBusy(false); }
  };
  const removePasskey = async (id) => {
    try { await deletePasskey(id); toast.success("Passkey removed"); await loadPasskeys(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not remove passkey"); }
  };

  const startEnroll = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/mfa/enroll");
      setEnroll(data);
      setPhase("enrolling");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start enrollment");
    } finally { setBusy(false); }
  };

  const activate = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/mfa/activate", { code: code.trim() });
      setBackupCodes(data.backup_codes || []);
      setCode("");
      setPhase("backup");
      toast.success("Two-factor authentication enabled");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invalid code");
    } finally { setBusy(false); }
  };

  const disable = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/mfa/disable", { code: code.trim() });
      setCode("");
      setPhase("view");
      toast.success("Two-factor authentication disabled");
      await loadStatus();
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invalid code");
    } finally { setBusy(false); }
  };

  const copyBackup = () => {
    navigator.clipboard?.writeText((backupCodes || []).join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="fixed inset-0 z-[60] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-md" data-testid="security-modal">
        <div className="px-5 py-4 border-b border-edge flex justify-between items-center">
          <h3 className="font-serif text-xl text-ink flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-clay" /> Account security</h3>
          <button onClick={onClose} className="text-2xl text-ink-soft leading-none">×</button>
        </div>

        <div className="p-5">
          {status === null ? (
            <div className="text-sm text-ink-soft">Loading…</div>
          ) : phase === "backup" ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-ink"><KeyRound className="w-4 h-4 text-clay" /><span className="font-medium">Save your backup codes</span></div>
              <p className="text-sm text-ink-soft">Store these somewhere safe. Each code works once if you ever lose your authenticator. They won't be shown again.</p>
              <div className="grid grid-cols-2 gap-2 rounded-md border border-edge bg-white/60 p-3 font-mono text-sm text-ink">
                {(backupCodes || []).map((c) => <div key={c} data-testid="backup-code">{c}</div>)}
              </div>
              <div className="flex justify-between items-center pt-1">
                <button onClick={copyBackup} className="inline-flex items-center gap-1.5 text-sm text-clay hover:text-clay-deep">
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />} {copied ? "Copied" : "Copy all"}
                </button>
                <button onClick={onClose} className="bg-clay text-white px-4 py-1.5 text-sm rounded-md">Done</button>
              </div>
            </div>
          ) : phase === "enrolling" ? (
            <form onSubmit={activate} className="space-y-4">
              <p className="text-sm text-ink-soft">In your authenticator app (Google Authenticator, Authy, 1Password…), add an account and enter this setup key:</p>
              <div className="rounded-md border border-edge bg-white/60 p-3">
                <div className="font-mono text-sm text-ink break-all tracking-wide" data-testid="mfa-secret">{enroll?.secret}</div>
              </div>
              <p className="text-[11px] text-ink-soft break-all">Or use the setup link: <span className="font-mono">{enroll?.otpauth_uri}</span></p>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">Enter the 6-digit code it shows</span>
                <input autoFocus inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ""))} maxLength={6} className={`${cls} mt-1 text-center text-lg tracking-[0.3em]`} data-testid="mfa-activate-input" placeholder="123456" />
              </label>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => { setPhase("view"); setCode(""); }} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
                <button type="submit" disabled={busy || code.length < 6} className="bg-clay text-white px-4 py-1.5 text-sm rounded-md disabled:opacity-50" data-testid="mfa-activate-btn">{busy ? "Verifying…" : "Turn on 2FA"}</button>
              </div>
            </form>
          ) : phase === "disabling" ? (
            <form onSubmit={disable} className="space-y-4">
              <div className="flex items-center gap-2 text-ink"><ShieldAlert className="w-4 h-4 text-clay-deep" /><span className="font-medium">Turn off two-factor authentication?</span></div>
              <p className="text-sm text-ink-soft">Enter a current code to confirm. Your account will be less protected.</p>
              <input autoFocus inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9A-Za-z-]/g, ""))} maxLength={14} className={`${cls} text-center text-lg tracking-[0.3em]`} data-testid="mfa-disable-input" placeholder="123456" />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => { setPhase("view"); setCode(""); }} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
                <button type="submit" disabled={busy || !code} className="bg-clay-deep text-white px-4 py-1.5 text-sm rounded-md disabled:opacity-50" data-testid="mfa-disable-btn">{busy ? "Disabling…" : "Disable 2FA"}</button>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                {status.enrolled
                  ? <ShieldCheck className="w-6 h-6 text-sage shrink-0" />
                  : <ShieldAlert className="w-6 h-6 text-clay shrink-0" />}
                <div>
                  <div className="font-medium text-ink">Two-factor authentication</div>
                  <div className="text-sm text-ink-soft">
                    {status.enrolled
                      ? <>On. A code from your authenticator is required at sign-in.{typeof status.backup_codes_remaining === "number" ? ` ${status.backup_codes_remaining} backup codes left.` : ""}</>
                      : "Off. Add a second factor so a stolen password isn't enough to sign in."}
                  </div>
                </div>
              </div>
              <div className="flex justify-end">
                {status.enrolled ? (
                  <button onClick={() => setPhase("disabling")} className="border border-edge text-ink px-4 py-1.5 text-sm rounded-md hover:bg-white/60" data-testid="mfa-disable-open">Disable</button>
                ) : (
                  <button onClick={startEnroll} disabled={busy} className="bg-clay text-white px-4 py-1.5 text-sm rounded-md disabled:opacity-50" data-testid="mfa-enroll-btn">{busy ? "Starting…" : "Enable 2FA"}</button>
                )}
              </div>

              {passkeySupported() && (
                <div className="border-t border-edge pt-4">
                  <div className="flex items-start gap-3">
                    <Fingerprint className="w-6 h-6 text-clay shrink-0" />
                    <div className="flex-1">
                      <div className="font-medium text-ink">Passkeys</div>
                      <div className="text-sm text-ink-soft">Sign in with your fingerprint, face, or device PIN — phishing-resistant, no code to type.</div>
                    </div>
                  </div>
                  {passkeys.length > 0 && (
                    <ul className="mt-3 space-y-2" data-testid="passkey-list">
                      {passkeys.map((p) => (
                        <li key={p.id} className="flex items-center justify-between rounded-md border border-edge bg-white/60 px-3 py-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <KeyRound className="w-4 h-4 text-ink-soft shrink-0" />
                            <span className="text-sm text-ink truncate">{p.label || "Passkey"}</span>
                          </div>
                          <button onClick={() => removePasskey(p.id)} className="text-ink-soft hover:text-clay-deep p-1" title="Remove passkey" data-testid="passkey-remove">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="mt-3 flex justify-end">
                    <button onClick={addPasskey} disabled={pkBusy} className="inline-flex items-center gap-1.5 border border-edge text-ink px-4 py-1.5 text-sm rounded-md hover:bg-white/60 disabled:opacity-50" data-testid="passkey-add-btn">
                      <Plus className="w-4 h-4" /> {pkBusy ? "Waiting…" : "Add a passkey"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

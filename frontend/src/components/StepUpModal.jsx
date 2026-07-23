/*
  <component name="StepUpProvider" layer="frontend">
    <purpose>
      Global re-authentication prompt (P1-9). Registers a handler on the shared
      api client; when a sensitive action returns 403 "step-up required", the
      interceptor calls the handler, which shows this modal, exchanges a fresh
      TOTP/backup code for a short-lived elevation token (POST /auth/mfa/step-up),
      and the original request is replayed with X-Step-Up-Token. Renders nothing
      until a step-up is actually requested.
    </purpose>
  </component>
*/
import { useEffect, useRef, useState } from "react";
import { api, setStepUpHandler } from "@/lib/api";
import { ShieldCheck } from "lucide-react";

const cls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-center text-lg tracking-[0.3em] focus:border-clay outline-none";

export default function StepUpProvider() {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resolver = useRef(null);

  useEffect(() => {
    setStepUpHandler(
      () =>
        new Promise((resolve) => {
          resolver.current = resolve;
          setCode("");
          setError("");
          setBusy(false);
          setOpen(true);
        })
    );
    return () => setStepUpHandler(null);
  }, []);

  const finish = (value) => {
    setOpen(false);
    const r = resolver.current;
    resolver.current = null;
    if (r) r(value);
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/auth/mfa/step-up", { code: code.trim() });
      finish(data.elevation_token); // interceptor replays the original request
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Invalid code");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] bg-ink/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-bone-paper border border-edge rounded-md w-full max-w-sm" data-testid="stepup-modal">
        <div className="px-5 py-4 border-b border-edge flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-clay" />
          <h3 className="font-serif text-xl text-ink">Confirm it's you</h3>
        </div>
        <form onSubmit={submit} className="p-5 space-y-3">
          <p className="text-sm text-ink-soft">
            This action needs a fresh security check. Enter a code from your authenticator app (or a backup code).
          </p>
          <input
            autoFocus
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/[^0-9A-Za-z-]/g, ""))}
            maxLength={14}
            className={cls}
            data-testid="stepup-input"
            placeholder="123456"
          />
          {error && (
            <div className="text-sm text-clay-deep bg-clay/10 border border-clay/30 rounded-md px-3 py-2" data-testid="stepup-error">
              {error}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => finish(null)} className="px-3 py-1.5 text-sm text-ink-soft">
              Cancel
            </button>
            <button type="submit" disabled={busy || !code} className="bg-clay text-white px-4 py-1.5 text-sm rounded-md disabled:opacity-50" data-testid="stepup-submit">
              {busy ? "Verifying…" : "Confirm"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

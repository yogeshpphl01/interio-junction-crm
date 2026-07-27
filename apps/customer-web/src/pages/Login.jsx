/*
  Customer login — phone + one-time code. Two steps:
    1) enter phone  -> POST /client/auth/request-otp (generic response)
    2) enter code   -> POST /client/auth/verify-otp   -> customer session
  Mirrors the Client mobile app. No password, no self-signup: a code is only
  delivered to a number that already exists as a lead in the CRM.
*/
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ArrowLeft, ShieldCheck, Phone } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import { Button, Input } from "@/components/ui";
import { prettyPhone } from "@/lib/format";

const RESEND_SECONDS = 60;

export default function Login() {
  const { customer, requestOtp, verifyOtp } = useAuth();
  const { push } = useToast();
  const navigate = useNavigate();

  const [step, setStep] = useState("phone"); // "phone" | "code"
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const codeRef = useRef(null);

  useEffect(() => {
    if (customer) navigate("/", { replace: true });
  }, [customer, navigate]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const digits = phone.replace(/\D/g, "").slice(-10);
  const phoneValid = digits.length === 10;
  const codeValid = code.replace(/\D/g, "").length === 4;

  async function sendCode(e) {
    e?.preventDefault();
    if (!phoneValid) return;
    setBusy(true);
    const res = await requestOtp(digits);
    setBusy(false);
    if (res.ok) {
      setStep("code");
      setCooldown(RESEND_SECONDS);
      setTimeout(() => codeRef.current?.focus(), 50);
      push({ title: "Code sent", description: "If your number is registered, a login code is on its way.", tone: "info" });
    } else {
      push({ title: "Couldn't send code", description: res.error, tone: "error" });
    }
  }

  async function verify(e) {
    e?.preventDefault();
    if (!codeValid) return;
    setBusy(true);
    const res = await verifyOtp(digits, code.trim());
    setBusy(false);
    if (res.ok) {
      navigate("/", { replace: true });
    } else {
      push({ title: "Invalid code", description: res.error, tone: "error" });
      setCode("");
    }
  }

  return (
    <div className="auth-backdrop flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-700 text-white shadow-card">
            <span className="text-xl font-bold">IJ</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Interio Junction</h1>
          <p className="mt-1 text-slate-500">Your project portal</p>
        </div>

        <div className="rounded-3xl border border-slate-100 bg-white p-6 shadow-card sm:p-8">
          {step === "phone" ? (
            <form onSubmit={sendCode} className="space-y-5">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Mobile number</label>
                <div className="relative">
                  <Phone className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                  <Input
                    type="tel"
                    inputMode="numeric"
                    autoComplete="tel"
                    placeholder="98765 43210"
                    className="pl-11"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    autoFocus
                  />
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  Use the number you shared with our team. We'll text you a login code.
                </p>
              </div>
              <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!phoneValid}>
                Send login code <ArrowRight className="h-4 w-4" />
              </Button>
            </form>
          ) : (
            <form onSubmit={verify} className="space-y-5">
              <button
                type="button"
                onClick={() => { setStep("phone"); setCode(""); }}
                className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
              >
                <ArrowLeft className="h-4 w-4" /> Change number
              </button>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Enter the 4-digit code</label>
                <p className="mb-3 text-sm text-slate-500">Sent to {prettyPhone(digits)}</p>
                <Input
                  ref={codeRef}
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={4}
                  placeholder="••••"
                  className="text-center text-2xl tracking-[0.6em]"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 4))}
                />
              </div>
              <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!codeValid}>
                <ShieldCheck className="h-4 w-4" /> Verify & sign in
              </Button>
              <div className="text-center text-sm">
                {cooldown > 0 ? (
                  <span className="text-slate-400">Resend code in {cooldown}s</span>
                ) : (
                  <button type="button" onClick={sendCode} className="font-medium text-brand-700 hover:text-brand-800">
                    Resend code
                  </button>
                )}
              </div>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">
          Trouble signing in? Contact your Interio Junction project manager.
        </p>
      </div>
    </div>
  );
}

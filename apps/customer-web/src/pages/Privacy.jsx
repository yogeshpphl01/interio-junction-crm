/*
  Privacy & consent (DPDP rights for the customer):
    • view/withdraw itemized consents (necessary shown locked; optional toggles) — POST /client/me/consent
    • change email / phone, verified by an OTP to the new value (item 9)
    • download a copy of my data (right to access) — GET /client/me/export
    • delete my data (item 10): enquiry-only = immediate; project client = queued
  Mirrors the backend consent catalog and rights endpoints.
*/
import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, Download, Trash2, Mail, Phone, Check, X, Lock } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/components/Toast";
import { Button, Card, CardBody, CardHeader, Input, PageLoader } from "@/components/ui";
import { cn } from "@/lib/utils";

function Toggle({ on, disabled, busy, onChange, testid }) {
  return (
    <button
      type="button"
      data-testid={testid}
      disabled={disabled || busy}
      onClick={() => onChange(!on)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors",
        on ? "bg-brand-600" : "bg-slate-300",
        (disabled || busy) && "opacity-50 cursor-not-allowed"
      )}
      aria-pressed={on}
    >
      <span className={cn("inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform", on ? "translate-x-5" : "translate-x-0.5")} />
    </button>
  );
}

function ChangeContactModal({ field, current, onClose, onDone }) {
  const { push } = useToast();
  const [step, setStep] = useState("enter"); // enter | verify
  const [value, setValue] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendCode(e) {
    e?.preventDefault();
    setBusy(true);
    try {
      await api.post("/client/me/change-contact", { field, new_value: value.trim() });
      setStep("verify");
      push({ title: "Code sent", description: `We sent a verification code to your new ${field}.`, tone: "info" });
    } catch (e) {
      push({ title: "Couldn't send code", description: apiError(e), tone: "error" });
    } finally { setBusy(false); }
  }
  async function verify(e) {
    e?.preventDefault();
    setBusy(true);
    try {
      await api.post("/client/me/change-contact/verify", { field, code: code.trim() });
      push({ title: `${field === "email" ? "Email" : "Phone"} updated`, tone: "success" });
      onDone();
    } catch (e) {
      push({ title: "Couldn't verify", description: apiError(e), tone: "error" });
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h3 className="text-base font-semibold text-slate-900">Change {field}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        {step === "enter" ? (
          <form onSubmit={sendCode} className="mt-4 space-y-3">
            <p className="text-sm text-slate-500">Current: <span className="font-medium text-slate-700">{current || "—"}</span></p>
            <Input
              type={field === "email" ? "email" : "tel"}
              inputMode={field === "email" ? "email" : "numeric"}
              placeholder={field === "email" ? "new@email.com" : "New 10-digit number"}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
            />
            <p className="text-xs text-slate-400">We'll send a one-time code to the new {field} to confirm it's yours.</p>
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
              <Button type="submit" loading={busy} disabled={!value.trim()}>Send code</Button>
            </div>
          </form>
        ) : (
          <form onSubmit={verify} className="mt-4 space-y-3">
            <p className="text-sm text-slate-500">Enter the code we sent to <span className="font-medium text-slate-700">{value}</span></p>
            <Input inputMode="numeric" maxLength={4} placeholder="••••" className="text-center text-xl tracking-[0.5em]"
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 4))} autoFocus />
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="secondary" onClick={() => setStep("enter")}>Back</Button>
              <Button type="submit" loading={busy} disabled={code.length < 4}>Verify & save</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default function Privacy() {
  const { customer, logout, refresh } = useAuth();
  const { push } = useToast();
  const [consent, setConsent] = useState(null);
  const [saving, setSaving] = useState(null);
  const [erasing, setErasing] = useState(false);
  const [confirmErase, setConfirmErase] = useState(false);
  const [changeField, setChangeField] = useState(null);

  const load = useCallback(async () => {
    try { setConsent((await api.get("/client/me/consent")).data); }
    catch (e) { push({ title: "Couldn't load consents", description: apiError(e), tone: "error" }); }
  }, [push]);
  useEffect(() => { load(); }, [load]);

  async function setConsentValue(purpose, granted) {
    setSaving(purpose);
    try { await api.post("/client/me/consent", { purpose, granted }); await load(); }
    catch (e) { push({ title: "Couldn't update", description: apiError(e), tone: "error" }); }
    finally { setSaving(null); }
  }

  async function exportData() {
    try {
      const { data } = await api.get("/client/me/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `interio-junction-my-data-${new Date().toISOString().slice(0, 10)}.json`; a.click();
      URL.revokeObjectURL(url);
      push({ title: "Download started", tone: "success" });
    } catch (e) { push({ title: "Couldn't export", description: apiError(e), tone: "error" }); }
  }

  async function eraseNow() {
    setErasing(true);
    try {
      const { data } = await api.post("/client/me/erasure-request", { reason: "customer requested via portal" });
      if (data.status === "erased") {
        push({ title: "Your data has been deleted", description: "You'll now be signed out.", tone: "success" });
        setTimeout(() => logout(), 1500);
      } else {
        push({ title: "Request received", description: data.message, tone: "info" });
        setConfirmErase(false);
      }
    } catch (e) { push({ title: "Couldn't process request", description: apiError(e), tone: "error" }); }
    finally { setErasing(false); }
  }

  if (!consent) return <PageLoader />;
  const cat = consent.catalog || {};
  const cur = consent.current || {};
  const purposes = Object.entries(cat);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Privacy &amp; consent</h1>
        <p className="mt-1 text-slate-500">Control how your data is used, update your details, or download/delete your data.</p>
      </div>

      {/* Consents */}
      <Card>
        <CardHeader title="How we use your data" subtitle="Turn optional uses on or off anytime. Required items are needed to run your project." />
        <CardBody className="space-y-1 pt-2">
          {purposes.map(([key, p]) => {
            const necessary = p.category === "necessary";
            const on = !!cur[key];
            return (
              <div key={key} className="flex items-start justify-between gap-4 border-t border-slate-100 py-3 first:border-t-0">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-800">{p.label}</span>
                    {necessary && <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500"><Lock className="h-3 w-3" /> Required</span>}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{p.description}</p>
                </div>
                <Toggle testid={`consent-${key}`} on={necessary ? true : on} disabled={necessary} busy={saving === key} onChange={(v) => setConsentValue(key, v)} />
              </div>
            );
          })}
          <p className="pt-2 text-[11px] text-slate-400">Policy version {consent.policy_version}. Your choices are logged with a timestamp.</p>
        </CardBody>
      </Card>

      {/* Contact details */}
      <Card>
        <CardHeader title="Your contact details" subtitle="Changing these needs a one-time code sent to the new value." />
        <CardBody className="space-y-3 pt-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><Mail className="h-4 w-4" /></div>
              <div><p className="text-xs text-slate-400">Email</p><p className="text-sm font-medium text-slate-800">{customer?.email || "—"}</p></div>
            </div>
            <Button variant="secondary" size="sm" data-testid="change-email-btn" onClick={() => setChangeField("email")}>Change</Button>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><Phone className="h-4 w-4" /></div>
              <div><p className="text-xs text-slate-400">Phone</p><p className="text-sm font-medium text-slate-800">{customer?.phone || "—"}</p></div>
            </div>
            <Button variant="secondary" size="sm" onClick={() => setChangeField("phone")}>Change</Button>
          </div>
        </CardBody>
      </Card>

      {/* Data rights */}
      <Card>
        <CardHeader title="Your data" subtitle="Access and deletion rights under the DPDP Act." />
        <CardBody className="space-y-3 pt-2">
          <div className="flex items-center justify-between gap-3">
            <div><p className="text-sm font-medium text-slate-800">Download a copy of my data</p><p className="text-xs text-slate-500">A structured export of everything we hold about you.</p></div>
            <Button variant="secondary" size="sm" data-testid="export-btn" onClick={exportData}><Download className="h-4 w-4" /> Export</Button>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <div><p className="text-sm font-medium text-rose-700">Delete my data</p><p className="text-xs text-slate-500">If you only enquired, this deletes your data now. If you have a project, we keep records for the warranty/legal period and log your request.</p></div>
            <Button variant="danger" size="sm" data-testid="delete-btn" onClick={() => setConfirmErase(true)}><Trash2 className="h-4 w-4" /> Delete</Button>
          </div>
        </CardBody>
      </Card>

      <p className="text-center text-xs text-slate-400">
        Questions or a privacy concern? Contact our team — details in the consent notice. You may also complain to the Data Protection Board of India.
      </p>

      {changeField && (
        <ChangeContactModal
          field={changeField}
          current={changeField === "email" ? customer?.email : customer?.phone}
          onClose={() => setChangeField(null)}
          onDone={async () => { setChangeField(null); await refresh(); }}
        />
      )}

      {confirmErase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => !erasing && setConfirmErase(false)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-rose-700"><Trash2 className="h-5 w-5" /><h3 className="text-base font-semibold">Delete my data?</h3></div>
            <p className="mt-2 text-sm text-slate-600">This can't be undone. If you only enquired with us, your personal data is deleted immediately and you'll be signed out. If you have an active project, we keep records for the warranty/legal period and log your request.</p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirmErase(false)} disabled={erasing}>Cancel</Button>
              <Button variant="danger" onClick={eraseNow} loading={erasing}>Yes, delete</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

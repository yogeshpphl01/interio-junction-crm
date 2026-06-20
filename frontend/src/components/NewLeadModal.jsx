import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function NewLeadModal({ onClose, onCreated }) {
  const [meta, setMeta] = useState(null);
  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    city: "",
    address: "",
    lead_type: "Retail Client",
    source: "Website",
    bhk_type: "2 BHK",
    kitchen_layout: "L-shape",
    tentative_budget: 0,
    requirements: "",
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/meta").then((r) => setMeta(r.data));
  }, []);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = { ...form, tentative_budget: Number(form.tentative_budget) || 0 };
      const { data } = await api.post("/leads", payload);
      onCreated(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create lead");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-bone-paper rounded-md border border-edge w-full max-w-2xl max-h-[90vh] overflow-y-auto scrollbar-thin"
        data-testid="new-lead-modal"
      >
        <div className="px-6 py-5 border-b border-edge flex items-center justify-between">
          <h3 className="font-serif text-2xl text-ink">New Lead</h3>
          <button onClick={onClose} className="text-ink-soft hover:text-ink text-2xl leading-none" data-testid="modal-close-btn">×</button>
        </div>
        <form className="px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-4" onSubmit={submit}>
          <Field label="Client name" required>
            <input data-testid="lead-full-name" required value={form.full_name} onChange={(e) => set("full_name", e.target.value)} className={inputCls} />
          </Field>
          <Field label="Phone" required>
            <input data-testid="lead-phone" required value={form.phone} onChange={(e) => set("phone", e.target.value)} className={inputCls} />
          </Field>
          <Field label="Email">
            <input data-testid="lead-email" value={form.email} onChange={(e) => set("email", e.target.value)} className={inputCls} />
          </Field>
          <Field label="City">
            <input data-testid="lead-city" value={form.city} onChange={(e) => set("city", e.target.value)} className={inputCls} />
          </Field>
          <Field label="Lead type">
            <select data-testid="lead-type" value={form.lead_type} onChange={(e) => set("lead_type", e.target.value)} className={inputCls}>
              {meta?.lead_types.map((x) => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="Source">
            <select data-testid="lead-source" value={form.source} onChange={(e) => set("source", e.target.value)} className={inputCls}>
              {meta?.lead_sources.map((x) => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="BHK">
            <select data-testid="lead-bhk" value={form.bhk_type} onChange={(e) => set("bhk_type", e.target.value)} className={inputCls}>
              {meta?.bhk_types.map((x) => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="Kitchen layout">
            <select data-testid="lead-kitchen" value={form.kitchen_layout} onChange={(e) => set("kitchen_layout", e.target.value)} className={inputCls}>
              {meta?.kitchen_layouts.map((x) => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="Tentative budget (₹)">
            <input data-testid="lead-budget" type="number" min={0} value={form.tentative_budget} onChange={(e) => set("tentative_budget", e.target.value)} className={inputCls} />
          </Field>
          <Field label="Address" className="sm:col-span-2">
            <input data-testid="lead-address" value={form.address} onChange={(e) => set("address", e.target.value)} className={inputCls} />
          </Field>
          <Field label="Requirements" className="sm:col-span-2">
            <textarea data-testid="lead-requirements" rows={3} value={form.requirements} onChange={(e) => set("requirements", e.target.value)} className={inputCls} />
          </Field>
          <div className="sm:col-span-2 flex items-center justify-end gap-2 pt-2 border-t border-edge">
            <button type="button" onClick={onClose} className="px-4 py-2 text-ink-soft hover:text-ink text-sm">Cancel</button>
            <button data-testid="submit-new-lead" disabled={busy} type="submit" className="bg-clay hover:bg-clay-deep disabled:opacity-50 text-white rounded-md px-4 py-2 text-sm font-medium">
              {busy ? "Saving…" : "Create lead"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const inputCls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay focus:ring-2 focus:ring-clay/20 outline-none";

function Field({ label, children, required, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">
        {label}{required && <span className="text-clay ml-0.5">*</span>}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

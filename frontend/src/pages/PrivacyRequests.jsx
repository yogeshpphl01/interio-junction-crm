/*
  <page name="PrivacyRequests" route="/privacy" access="users.manage">
    <purpose>
      Staff queue for DPDP data-subject erasure requests. Lists requests and lets
      an admin ERASE (anonymize the customer + leads, retaining transactional rows
      per DPDP §8(7)) or REJECT (e.g. an active project / outstanding dues). Erase
      is a privileged, destructive act, so the backend requires a fresh step-up —
      the global step-up prompt handles that automatically.
    </purpose>
  </page>
*/
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { ShieldCheck, Trash2, XCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { fmtDate } from "@/lib/format";

const TABS = [
  { key: "pending", label: "Pending" },
  { key: "completed", label: "Completed" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All" },
];

export default function PrivacyRequests() {
  const [rows, setRows] = useState(null);
  const [tab, setTab] = useState("pending");
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try { setRows((await api.get(`/erasure-requests?status=${tab}`)).data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed to load requests"); }
  }, [tab]);
  useEffect(() => { load(); }, [load]);

  const erase = async (r) => {
    if (!window.confirm(`Erase ${r.customer_name || "this customer"}'s personal data?\n\nName, phone and email are anonymized across their record and leads. Transactional records (invoices etc.) are retained as the law requires. This cannot be undone.`)) return;
    setBusy(r.id);
    try {
      await api.post(`/customers/${r.customer_id}/erase`);
      toast.success("Customer data erased");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not erase");
    } finally { setBusy(null); }
  };

  const reject = async (r) => {
    if (!window.confirm("Reject this erasure request? (e.g. active project or outstanding dues). The decision is recorded.")) return;
    setBusy(r.id);
    try {
      await api.post(`/erasure-requests/${r.id}/reject`, {});
      toast.success("Request rejected");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not reject");
    } finally { setBusy(null); }
  };

  const badge = (s) => ({
    pending: "bg-clay/10 text-clay-deep border-clay/30",
    completed: "bg-[#4A5D23]/10 text-[#4A5D23] border-[#4A5D23]/30",
    rejected: "bg-ink/5 text-ink-soft border-edge",
  }[s] || "bg-ink/5 text-ink-soft border-edge");

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6 max-w-5xl">
      <Toaster richColors position="top-right" />
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-clay" /> Privacy requests
          </h2>
          <p className="text-ink-soft text-sm mt-2">
            DPDP erasure requests from customers. Erasing anonymizes personal data while retaining
            transactional records the business must keep (DPDP §8(7)).
          </p>
        </div>
        <button onClick={load} className="p-2 rounded hover:bg-bone-subtle text-ink-soft" title="Refresh" data-testid="privacy-refresh">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="flex gap-1 mb-4">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)} data-testid={`privacy-tab-${t.key}`}
            className={`px-3 py-1.5 text-sm rounded-md border ${tab === t.key ? "bg-clay text-white border-clay" : "border-edge text-ink-soft hover:bg-bone-subtle"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {rows === null ? (
        <div className="text-ink-muted text-sm py-10">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="bg-bone-paper border border-edge rounded-md p-10 text-center text-ink-soft" data-testid="privacy-empty">
          No {tab === "all" ? "" : tab} requests.
        </div>
      ) : (
        <div className="bg-bone-paper border border-edge rounded-md overflow-hidden" data-testid="privacy-list">
          <table className="w-full text-sm">
            <thead className="bg-bone-subtle text-left text-[11px] uppercase tracking-wide text-ink-soft">
              <tr>
                <th className="px-4 py-2.5 font-semibold">Customer</th>
                <th className="px-4 py-2.5 font-semibold">Requested</th>
                <th className="px-4 py-2.5 font-semibold">Reason</th>
                <th className="px-4 py-2.5 font-semibold">Status</th>
                <th className="px-4 py-2.5 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-3 text-ink">{r.customer_name || r.customer_id}{r.already_erased && <span className="ml-2 text-[10px] text-ink-muted">(erased)</span>}</td>
                  <td className="px-4 py-3 text-ink-soft">{fmtDate(r.requested_at)}</td>
                  <td className="px-4 py-3 text-ink-soft max-w-[16rem] truncate" title={r.reason}>{r.reason || "—"}</td>
                  <td className="px-4 py-3"><span className={`inline-block px-2 py-0.5 text-[11px] rounded-full border capitalize ${badge(r.status)}`}>{r.status}</span></td>
                  <td className="px-4 py-3 text-right">
                    {r.status === "pending" ? (
                      <div className="inline-flex gap-2">
                        <button onClick={() => reject(r)} disabled={busy === r.id} data-testid="privacy-reject"
                          className="inline-flex items-center gap-1 border border-edge text-ink px-2.5 py-1.5 text-xs rounded-md hover:bg-bone-subtle disabled:opacity-50">
                          <XCircle className="w-3.5 h-3.5" /> Reject
                        </button>
                        <button onClick={() => erase(r)} disabled={busy === r.id || r.already_erased} data-testid="privacy-erase"
                          className="inline-flex items-center gap-1 bg-clay-deep text-white px-2.5 py-1.5 text-xs rounded-md hover:opacity-90 disabled:opacity-50">
                          <Trash2 className="w-3.5 h-3.5" /> Erase
                        </button>
                      </div>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Actioned
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

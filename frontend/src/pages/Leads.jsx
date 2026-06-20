import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { formatINR, timeAgo, initials } from "@/lib/format";
import { StageBadge, HeatChip, LifecycleBadge } from "@/components/StageVisuals";
import { LIFECYCLE } from "@/lib/constants";
import ImportLeadsModal from "@/components/ImportLeadsModal";
import { Toaster } from "sonner";
import { Search, UploadCloud } from "lucide-react";

export default function Leads() {
  const { user } = useAuth();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [lifecycle, setLifecycle] = useState("");   // NEW: client-side journey filter
  const [showImport, setShowImport] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);     // bump to re-fetch after import

  const canImport = user && (user.role === "admin" || user.role === "sales");

  useEffect(() => {
    setLoading(true);
    const params = {};
    if (stage) params.stage = Number(stage);
    if (status) params.status = status;
    api
      .get("/leads", { params })
      .then((r) => setLeads(r.data))
      .finally(() => setLoading(false));
  }, [stage, status, reloadKey]);

  // Search + lifecycle filtering happen client-side on the fetched rows.
  const filtered = leads.filter(
    (l) =>
      (!q || (l.full_name + " " + (l.city || "") + " " + (l.project?.project_code || "")).toLowerCase().includes(q.toLowerCase())) &&
      (!lifecycle || l.lifecycle_phase === lifecycle)
  );

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Leads</h2>
          <p className="text-ink-muted text-sm mt-2">{filtered.length} of {leads.length}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input data-testid="leads-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" className="bg-bone-paper border border-edge rounded-md pl-9 pr-3 py-2 text-sm w-56 focus:border-clay outline-none" />
          </div>
          <select value={stage} onChange={(e) => setStage(e.target.value)} className="bg-bone-paper border border-edge rounded-md px-2.5 py-2 text-sm" data-testid="filter-stage">
            <option value="">All stages</option>
            {[1, 2, 3, 4, 5, 6].map((s) => <option key={s} value={s}>Stage {s}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="bg-bone-paper border border-edge rounded-md px-2.5 py-2 text-sm" data-testid="filter-status">
            <option value="">All statuses</option>
            {["Active", "Won", "Lost", "On-hold"].map((s) => <option key={s}>{s}</option>)}
          </select>
          {/* NEW: filter by journey lifecycle bucket */}
          <select value={lifecycle} onChange={(e) => setLifecycle(e.target.value)} className="bg-bone-paper border border-edge rounded-md px-2.5 py-2 text-sm" data-testid="filter-lifecycle">
            <option value="">All journeys</option>
            {LIFECYCLE.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
          {/* NEW: import leads from a Meta Lead-Ads spreadsheet (admin/sales only) */}
          {canImport && (
            <button
              onClick={() => setShowImport(true)}
              data-testid="open-import-modal"
              className="inline-flex items-center gap-1.5 bg-clay hover:bg-clay-deep text-white rounded-md px-3 py-2 text-sm font-medium"
            >
              <UploadCloud className="w-4 h-4" /> Import
            </button>
          )}
        </div>
      </div>

      <div className="bg-bone-paper border border-edge rounded-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-bone-subtle text-ink-soft">
              <tr className="text-left">
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Client</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Stage</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Journey</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Type</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Budget</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Score</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Owner</th>
                <th className="px-4 py-2.5 font-medium text-[11px] uppercase tracking-wider">Updated</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={8} className="text-center py-10 text-ink-muted">Loading…</td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr><td colSpan={8} className="text-center py-10 text-ink-muted italic">No leads</td></tr>
              )}
              {filtered.map((l) => (
                <tr key={l.id} className="border-t border-edge hover:bg-bone transition" data-testid={`lead-row-${l.id}`}>
                  <td className="px-4 py-3">
                    <Link to={`/leads/${l.id}`} className="font-medium text-ink hover:text-clay">{l.full_name}</Link>
                    <div className="text-[11px] text-ink-muted">{l.city || "—"} {l.project?.project_code && `· ${l.project.project_code}`}</div>
                  </td>
                  <td className="px-4 py-3"><StageBadge stage={l.stage} /></td>
                  <td className="px-4 py-3"><LifecycleBadge phase={l.lifecycle_phase} /></td>
                  <td className="px-4 py-3 text-ink-soft">{l.lead_type}</td>
                  <td className="px-4 py-3 font-mono text-ink">{formatINR(l.tentative_budget)}</td>
                  <td className="px-4 py-3"><HeatChip heat={l.heat} score={l.score} /></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-walnut text-white text-[10px] font-semibold flex items-center justify-center">{initials(l.owner?.full_name || "—")}</div>
                      <span className="text-ink-soft">{l.owner?.full_name?.split(" ")[0] || "—"}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{timeAgo(l.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* NEW: Excel / Meta Lead-Ads import modal (refreshes the table on success) */}
      {showImport && (
        <ImportLeadsModal
          onClose={() => setShowImport(false)}
          onImported={() => setReloadKey((k) => k + 1)}
        />
      )}
    </div>
  );
}

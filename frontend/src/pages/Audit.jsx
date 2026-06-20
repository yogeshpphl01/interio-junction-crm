import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { timeAgo, fmtDate, initials } from "@/lib/format";
import { Search, ChevronLeft, ChevronRight, Activity } from "lucide-react";
import { Toaster } from "sonner";

const ACTION_ACCENT = {
  "auth.login": "#8A9A5B",
  "auth.login_failed": "#A95A3F",
  "auth.logout": "#8A817C",
  "lead.created": "#D4A373",
  "lead.updated": "#D4A373",
  "lead.stage_changed": "#9C6644",
  "lead.closed_won": "#4A5D23",
  "lead.closed_lost": "#A95A3F",
  "lead.on_hold": "#8A817C",
  "lead.reopened": "#8A9A5B",
  "project.created": "#6B705C",
  "measurement.created": "#6B705C",
  "measurement.updated": "#6B705C",
  "measurement.completed": "#8A9A5B",
  "revision.created": "#9C6644",
  "revision.updated": "#9C6644",
  "revision.status_changed": "#9C6644",
  "payment.created": "#A95A3F",
  "payment.paid": "#4A5D23",
  "payment.updated": "#A95A3F",
  "document.uploaded": "#C2683D",
  "document.downloaded": "#C2683D",
  "user.created": "#8A5A3B",
  "user.updated": "#8A5A3B",
  "automation.toggled": "#8A5A3B",
  "automation.run_checks": "#8A5A3B",
  "scoring.weights_saved": "#8A5A3B",
  "notification.sent": "#8A9A5B",
  "notification.failed": "#A95A3F",
};

const PAGE_SIZE = 50;

export default function Audit() {
  const [data, setData] = useState({ total: 0, rows: [], offset: 0 });
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [actions, setActions] = useState([]);
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE };
      if (q) params.q = q;
      if (action) params.action = action;
      const { data } = await api.get("/audit", { params });
      setData(data);
    } finally {
      setLoading(false);
    }
  }, [q, action, page]);

  useEffect(() => {
    api.get("/audit/actions").then((r) => setActions(r.data.actions || []));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Audit Log</h2>
          <p className="text-ink-muted text-sm mt-2">
            {data.total.toLocaleString("en-IN")} total events · admin only · every action is recorded
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              data-testid="audit-search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
              }}
              placeholder="Search actor, target, action…"
              className="bg-bone-paper border border-edge rounded-md pl-9 pr-3 py-2 text-sm w-64 focus:border-clay outline-none"
            />
          </div>
          <select
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(0);
            }}
            data-testid="audit-action-filter"
            className="bg-bone-paper border border-edge rounded-md px-2.5 py-2 text-sm"
          >
            <option value="">All actions</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-bone-paper border border-edge rounded-md overflow-hidden">
        {loading ? (
          <div className="p-10 text-center text-ink-muted">Loading…</div>
        ) : data.rows.length === 0 ? (
          <div className="p-12 text-center">
            <Activity className="w-8 h-8 mx-auto text-ink-muted mb-3" strokeWidth={1.5} />
            <div className="font-serif text-xl text-ink">No audit events</div>
            <div className="text-sm text-ink-muted mt-1">Try removing filters.</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bone-subtle text-ink-soft">
                <tr className="text-left">
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">When</th>
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Actor</th>
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Action</th>
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Target</th>
                  <th className="px-4 py-2.5 text-[11px] uppercase tracking-wider font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => {
                  const accent = ACTION_ACCENT[r.action] || "#8A817C";
                  return (
                    <tr key={r.id} className="border-t border-edge hover:bg-bone" data-testid={`audit-row-${r.id}`}>
                      <td className="px-4 py-3 align-top whitespace-nowrap">
                        <div className="text-ink text-xs">{timeAgo(r.created_at)}</div>
                        <div className="text-[10px] text-ink-muted font-mono">{fmtDate(r.created_at, true)}</div>
                      </td>
                      <td className="px-4 py-3 align-top">
                        {r.actor_name ? (
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-md bg-walnut text-white text-[10px] font-semibold flex items-center justify-center">
                              {initials(r.actor_name)}
                            </div>
                            <div className="min-w-0">
                              <div className="text-ink truncate">{r.actor_name}</div>
                              <div className="text-[10px] text-ink-muted truncate">{r.actor_role}</div>
                            </div>
                          </div>
                        ) : (
                          <span className="text-ink-muted italic text-xs">system</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top whitespace-nowrap">
                        <span
                          className="text-[11px] font-mono px-1.5 py-0.5 rounded"
                          style={{ background: `${accent}22`, color: accent, border: `1px solid ${accent}33` }}
                        >
                          {r.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <div className="text-ink text-xs">{r.target_label || "—"}</div>
                        <div className="text-[10px] text-ink-muted">{r.target_type}</div>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <MetaPills metadata={r.metadata} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-4 text-xs text-ink-soft">
        <div>
          Page {page + 1} of {totalPages}
        </div>
        <div className="flex items-center gap-1">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            data-testid="audit-prev"
            className="px-2 py-1 border border-edge rounded hover:bg-bone-subtle disabled:opacity-40"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            disabled={page + 1 >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            data-testid="audit-next"
            className="px-2 py-1 border border-edge rounded hover:bg-bone-subtle disabled:opacity-40"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function MetaPills({ metadata }) {
  if (!metadata || Object.keys(metadata).length === 0) return <span className="text-ink-muted text-xs">—</span>;
  const entries = Object.entries(metadata).slice(0, 4);
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => {
        let display = v;
        if (typeof v === "object") {
          display = Array.isArray(v) ? v.join(", ") : JSON.stringify(v);
        }
        const s = String(display);
        const short = s.length > 36 ? `${s.slice(0, 34)}…` : s;
        return (
          <span key={k} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bone-subtle border border-edge text-ink-soft" title={`${k}: ${s}`}>
            <span className="text-ink-muted">{k}:</span> {short}
          </span>
        );
      })}
    </div>
  );
}

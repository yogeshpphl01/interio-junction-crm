import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { fmtDate, formatINR } from "@/lib/format";
import { Toaster, toast } from "sonner";
import { Ruler, CheckCircle2 } from "lucide-react";

export default function SiteVisits() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/measurements");
      setItems(data);
    } catch (e) {
      toast.error("Failed to load");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const markCompleted = async (id) => {
    try {
      await api.patch(`/measurements/${id}`, { status: "Completed", completed_at: new Date().toISOString() });
      toast.success("Marked completed");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="mb-6">
        <h2 className="font-serif text-3xl text-ink leading-none">Site Visits</h2>
        <p className="text-ink-muted text-sm mt-2">{items.length} scheduled or completed measurements</p>
      </div>

      {loading ? (
        <div className="text-ink-muted">Loading…</div>
      ) : items.length === 0 ? (
        <div className="bg-bone-paper border border-edge rounded-md p-12 text-center">
          <Ruler className="w-8 h-8 mx-auto text-ink-muted mb-3" strokeWidth={1.5} />
          <div className="font-serif text-xl text-ink">No site visits yet</div>
          <div className="text-sm text-ink-muted mt-1">Move a lead to "Site Measurement" stage to schedule one.</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((m) => (
            <div key={m.id} className="bg-bone-paper border border-edge rounded-md p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-serif text-lg text-ink leading-tight">
                    {m.lead?.full_name || "—"}
                  </div>
                  <div className="text-[11px] font-mono text-ink-muted mt-0.5">
                    {m.project?.project_code} · {fmtDate(m.scheduled_at, true)}
                  </div>
                </div>
                <StatusPill status={m.status} />
              </div>
              <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
                <div>
                  <div className="text-[10px] uppercase text-ink-muted">Area</div>
                  <div className="text-ink">{m.total_area_sqft ? `${m.total_area_sqft} sqft` : "—"}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase text-ink-muted">Ceiling</div>
                  <div className="text-ink">{m.ceiling_height ? `${m.ceiling_height} ft` : "—"}</div>
                </div>
              </div>
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-edge">
                <Link to={`/leads/${m.lead?.id}`} className="text-xs text-clay hover:text-clay-deep" data-testid={`visit-open-${m.id}`}>
                  Open lead →
                </Link>
                {m.status !== "Completed" && (
                  <button
                    onClick={() => markCompleted(m.id)}
                    data-testid={`visit-complete-${m.id}`}
                    className="inline-flex items-center gap-1 text-xs text-stage-2 hover:underline"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" /> Mark completed
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    Completed: ["#8A9A5B22", "#5A6F2D"],
    "In Progress": ["#D4A37322", "#A56A2E"],
    Scheduled: ["#6B705C22", "#6B705C"],
  };
  const [bg, color] = map[status] || ["#8A817C22", "#8A817C"];
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ background: bg, color }}>
      {status}
    </span>
  );
}

import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { STAGES } from "@/lib/constants";
import { formatINR, initials, timeAgo } from "@/lib/format";
import { StageDot, HeatChip } from "@/components/StageVisuals";
import { toast, Toaster } from "sonner";
import { Plus, Search } from "lucide-react";
import NewLeadModal from "@/components/NewLeadModal";
import { useAuth } from "@/contexts/AuthContext";

export default function Pipeline() {
  const { user } = useAuth();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dragging, setDragging] = useState(null);
  const [hoverCol, setHoverCol] = useState(null);
  const [query, setQuery] = useState("");
  const [showNew, setShowNew] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/leads");
      setLeads(data);
    } catch (e) {
      toast.error("Failed to load leads");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(
    () =>
      leads.filter((l) =>
        !query
          ? true
          : (l.full_name + " " + (l.city || "") + " " + (l.project?.project_code || ""))
              .toLowerCase()
              .includes(query.toLowerCase())
      ),
    [leads, query]
  );

  const grouped = useMemo(() => {
    const g = Object.fromEntries(STAGES.map((s) => [s.id, []]));
    filtered.forEach((l) => g[l.stage]?.push(l));
    return g;
  }, [filtered]);

  const onDragStart = (lead) => setDragging(lead);
  const onDragEnd = () => {
    setDragging(null);
    setHoverCol(null);
  };
  const onDrop = async (stageId) => {
    if (!dragging) return;
    if (dragging.stage === stageId) return;
    const targetStage = stageId;
    const lead = dragging;
    try {
      const { data } = await api.post(`/leads/${lead.id}/move`, { to_stage: targetStage });
      setLeads((prev) => prev.map((l) => (l.id === lead.id ? data : l)));
      toast.success(`Moved → ${STAGES.find((s) => s.id === targetStage).short}`);
    } catch (e) {
      const detail = e?.response?.data?.detail || "Move failed";
      toast.error(detail);
    } finally {
      setDragging(null);
      setHoverCol(null);
    }
  };

  const canCreate = user?.role === "admin" || user?.role === "sales";

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Pipeline</h2>
          <p className="text-ink-muted text-sm mt-2">
            {filtered.length} {filtered.length === 1 ? "lead" : "leads"} · drag cards across stages
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              data-testid="pipeline-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, city, code…"
              className="bg-bone-paper border border-edge rounded-md pl-9 pr-3 py-2 text-sm w-64 focus:border-clay outline-none"
            />
          </div>
          {canCreate && (
            <button
              onClick={() => setShowNew(true)}
              data-testid="new-lead-btn"
              className="inline-flex items-center gap-2 bg-clay hover:bg-clay-deep text-white rounded-md px-3 py-2 text-sm font-medium transition"
            >
              <Plus className="w-4 h-4" /> New Lead
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-ink-muted">Loading pipeline…</div>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin -mx-2 px-2">
          {STAGES.map((s) => {
            const cards = grouped[s.id] || [];
            const total = cards.reduce((a, b) => a + (b.tentative_budget || 0), 0);
            const isOver = hoverCol === s.id;
            return (
              <div
                key={s.id}
                onDragOver={(e) => {
                  e.preventDefault();
                  setHoverCol(s.id);
                }}
                onDragLeave={() => setHoverCol((v) => (v === s.id ? null : v))}
                onDrop={() => onDrop(s.id)}
                className={`shrink-0 w-[320px] bg-bone-paper border rounded-md flex flex-col transition-all ${
                  isOver ? "border-clay shadow-md" : "border-edge"
                }`}
                data-testid={`kanban-col-${s.id}`}
              >
                <div className="px-4 py-3 border-b border-edge flex items-center justify-between sticky top-0 bg-bone-paper rounded-t-md z-10">
                  <div className="flex items-center gap-2 min-w-0">
                    <StageDot stage={s.id} />
                    <div className="font-serif text-sm text-ink truncate">{s.short}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-ink-muted">{cards.length}</span>
                    <span className="text-[11px] font-mono text-ink-soft">{formatINR(total)}</span>
                  </div>
                </div>
                <div className="p-3 space-y-3 min-h-[200px] flex-1 overflow-y-auto scrollbar-thin max-h-[calc(100vh-260px)]">
                  {cards.length === 0 && (
                    <div className="text-center text-[11px] text-ink-muted py-8 italic">No leads yet</div>
                  )}
                  {cards.map((l) => (
                    <KanbanCard key={l.id} lead={l} onDragStart={onDragStart} onDragEnd={onDragEnd} dragging={dragging?.id === l.id} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showNew && (
        <NewLeadModal
          onClose={() => setShowNew(false)}
          onCreated={(newLead) => {
            setLeads((prev) => [newLead, ...prev]);
            setShowNew(false);
            toast.success("Lead created");
          }}
        />
      )}
    </div>
  );
}

function KanbanCard({ lead, onDragStart, onDragEnd, dragging }) {
  return (
    <Link
      to={`/leads/${lead.id}`}
      draggable
      onDragStart={() => onDragStart(lead)}
      onDragEnd={onDragEnd}
      data-testid={`kanban-card-${lead.id}`}
      className={`block bg-bone-paper border border-edge rounded-md p-3 hover:border-bone-deep hover:shadow-sm transition cursor-grab active:cursor-grabbing ${
        dragging ? "kanban-card-dragging" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="font-medium text-ink text-sm leading-tight truncate">{lead.full_name}</div>
        <HeatChip heat={lead.heat} score={lead.score} />
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        <Chip>{lead.lead_type}</Chip>
        <Chip>{lead.bhk_type}</Chip>
        <Chip>{lead.kitchen_layout}</Chip>
      </div>
      <div className="font-serif text-lg text-ink">{formatINR(lead.tentative_budget)}</div>
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-full bg-walnut text-white text-[10px] font-semibold flex items-center justify-center">
            {initials(lead.owner?.full_name || "—")}
          </div>
          <span className="text-[11px] text-ink-muted truncate">{lead.owner?.full_name?.split(" ")[0] || "Unassigned"}</span>
        </div>
        {lead.project?.project_code ? (
          <span className="text-[10px] font-mono text-ink-soft bg-bone-subtle px-1.5 py-0.5 rounded">
            {lead.project.project_code}
          </span>
        ) : (
          <span className="text-[10px] text-ink-muted">{timeAgo(lead.updated_at)}</span>
        )}
      </div>
    </Link>
  );
}

function Chip({ children }) {
  return (
    <span className="px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded bg-bone-subtle text-ink-soft border border-edge">
      {children}
    </span>
  );
}

/*
  <page name="LeadScoring" route="/scoring" access="admin,sales">
    <purpose>Transparent scoring workbench: ranked leads with a per-signal "Why?"
    breakdown (GET /scoring), live weight sliders, and admin save of the default
    weights (POST /scoring/weights).</purpose>
  </page>
*/
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { formatINR } from "@/lib/format";
import { HeatChip } from "@/components/StageVisuals";
import { toast, Toaster } from "sonner";
import { ChevronDown, ChevronUp, RotateCcw, Save } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const SIGNAL_LABELS = {
  budget_tier: "Budget Tier",
  lead_type: "Lead Type",
  source_quality: "Source Quality",
  pipeline_progress: "Pipeline Progress",
  engagement: "Engagement",
  recency: "Recency",
};
const DEFAULT_WEIGHTS = {
  budget_tier: 25,
  lead_type: 15,
  source_quality: 10,
  pipeline_progress: 25,
  engagement: 15,
  recency: 10,
};

export default function LeadScoring() {
  const { user } = useAuth();
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [data, setData] = useState(null);
  const [open, setOpen] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (w = weights) => {
    setLoading(true);
    try {
      const { data } = await api.get("/scoring", { params: { weights: JSON.stringify(w) } });
      setData(data);
    } catch (e) {
      toast.error("Failed to load scoring");
    } finally {
      setLoading(false);
    }
  }, [weights]);

  useEffect(() => {
    api.get("/scoring/weights").then((r) => {
      const w = r.data.weights || DEFAULT_WEIGHTS;
      setWeights(w);
      load(w);
    });
  }, []);

  const totalW = Object.values(weights).reduce((a, b) => a + b, 0);

  const setW = (key, val) => {
    const v = Math.max(0, Math.min(100, Number(val)));
    const next = { ...weights, [key]: v };
    setWeights(next);
    load(next);
  };

  const reset = () => {
    setWeights(DEFAULT_WEIGHTS);
    load(DEFAULT_WEIGHTS);
  };
  const save = async () => {
    setSaving(true);
    try {
      await api.post("/scoring/weights", weights);
      toast.success("Weights saved");
    } catch (e) {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const isAdmin = user?.role === "admin";

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Lead Scoring</h2>
          <p className="text-ink-muted text-sm mt-2 max-w-xl">
            Transparent 0–100 score. Adjust signal weights to recompute live. Every contribution is auditable.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={reset} data-testid="reset-weights" className="inline-flex items-center gap-1 text-xs px-3 py-2 border border-edge rounded-md text-ink-soft hover:bg-bone-subtle">
            <RotateCcw className="w-3.5 h-3.5" /> Reset
          </button>
          {isAdmin && (
            <button onClick={save} disabled={saving} data-testid="save-weights" className="inline-flex items-center gap-1 text-xs px-3 py-2 bg-clay text-white rounded-md disabled:opacity-50">
              <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save as default"}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <aside className="col-span-12 lg:col-span-4 bg-bone-paper border border-edge rounded-md p-5 h-fit sticky top-24">
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-muted font-semibold mb-3">
            Signal weights · total {totalW}
          </div>
          <div className="space-y-4">
            {Object.entries(weights).map(([k, v]) => (
              <div key={k}>
                <div className="flex justify-between items-baseline mb-1">
                  <label className="text-sm text-ink">{SIGNAL_LABELS[k]}</label>
                  <span className="font-mono text-sm text-clay">{v}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={50}
                  value={v}
                  onChange={(e) => setW(k, e.target.value)}
                  className="clay-slider w-full"
                  data-testid={`weight-${k}`}
                />
              </div>
            ))}
          </div>
          <div className="mt-5 pt-4 border-t border-edge text-[11px] text-ink-muted leading-relaxed">
            Scores are normalized to 0–100. Drag any slider — the right panel recomputes live. No black-box model; every signal's points are explicit.
          </div>
        </aside>

        <section className="col-span-12 lg:col-span-8 space-y-2">
          {loading || !data ? (
            <div className="text-ink-muted">Loading…</div>
          ) : (
            data.leads.map((l, idx) => (
              <div key={l.lead_id} className="bg-bone-paper border border-edge rounded-md">
                <div className="px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono text-xs text-ink-muted w-6">#{idx + 1}</span>
                    <div className="min-w-0">
                      <Link to={`/leads/${l.lead_id}`} className="text-sm font-medium text-ink hover:text-clay truncate" data-testid={`score-row-${l.lead_id}`}>
                        {l.full_name}
                      </Link>
                      <div className="text-[11px] text-ink-muted">{l.lead_type} · Stage {l.stage} · {formatINR(l.tentative_budget)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="hidden sm:block w-32 h-1.5 bg-bone-subtle rounded-full overflow-hidden">
                      <div className="h-full" style={{ width: `${l.score}%`, background: l.heat === "Hot" ? "#C2683D" : l.heat === "Warm" ? "#D4A373" : "#6B705C" }} />
                    </div>
                    <HeatChip heat={l.heat} score={l.score} />
                    <button
                      onClick={() => setOpen((p) => ({ ...p, [l.lead_id]: !p[l.lead_id] }))}
                      data-testid={`score-why-${l.lead_id}`}
                      className="text-xs text-clay hover:text-clay-deep inline-flex items-center gap-1"
                    >
                      Why? {open[l.lead_id] ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
                {open[l.lead_id] && (
                  <div className="border-t border-edge px-4 py-3 bg-bone">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      {l.signals.map((s) => (
                        <div key={s.key} className="flex items-center justify-between bg-bone-paper border border-edge rounded px-3 py-2">
                          <div>
                            <div className="text-ink font-medium">{s.label}</div>
                            <div className="text-[11px] text-ink-muted">{s.raw} · weight {s.weight}</div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono text-clay text-sm">+{s.points}</div>
                            <div className="text-[10px] text-ink-muted">×{s.ratio}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}

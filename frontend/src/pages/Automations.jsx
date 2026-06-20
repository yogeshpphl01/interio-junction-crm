import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { toast, Toaster } from "sonner";
import { Workflow, Shield, Radio, Zap, AlertTriangle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const ICONS = {
  auto_assign_supervisor: Workflow,
  sla_breach_48h: AlertTriangle,
  notify_designer_revision: Radio,
  escalate_hot_lead: Zap,
};

export default function Automations() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [a, s] = await Promise.all([
        api.get("/automations"),
        api.get("/automations/signals", { params: { limit: 30 } }),
      ]);
      setItems(a.data);
      setSignals(s.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const toggle = async (key, enabled) => {
    if (user?.role !== "admin") return toast.error("Only admin can change automations");
    try {
      await api.patch(`/automations/${key}`, { enabled });
      toast.success(`${enabled ? "Enabled" : "Paused"}`);
      load();
    } catch (e) {
      toast.error("Failed");
    }
  };

  const runChecks = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/automations/run-checks");
      toast.success(`Fired ${data.fired} new signal${data.fired === 1 ? "" : "s"}`);
      load();
    } catch (e) {
      toast.error("Failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6">
      <Toaster richColors position="top-right" />
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h2 className="font-serif text-3xl text-ink leading-none">Automations</h2>
          <p className="text-ink-muted text-sm mt-2 max-w-2xl">
            Blueprint stage-gates and workflow rules. Gates block invalid stage moves; rules run on schedule and on events.
          </p>
        </div>
        <button onClick={runChecks} disabled={running} data-testid="run-checks-btn" className="text-xs bg-clay text-white rounded-md px-3 py-2 disabled:opacity-50">
          {running ? "Running…" : "Run checks now"}
        </button>
      </div>

      {/* Blueprint gates */}
      <section className="mb-8">
        <h3 className="font-serif text-xl text-ink mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-clay" /> Blueprint Stage Gates
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <GateCard
            title="Site Measurement → Design"
            rule="At least one Site Measurement marked Completed"
            stages={[3, 4]}
          />
          <GateCard
            title="Design → Quotation"
            rule="At least one Design Revision marked Approved"
            stages={[4, 5]}
          />
          <GateCard
            title="Quotation → Factory"
            rule="Signed-off + ≥ 50% milestone payments Paid"
            stages={[5, 6]}
          />
        </div>
      </section>

      <div className="grid grid-cols-12 gap-6">
        <section className="col-span-12 lg:col-span-7">
          <h3 className="font-serif text-xl text-ink mb-3 flex items-center gap-2">
            <Workflow className="w-4 h-4 text-clay" /> Workflow Rules
          </h3>
          <div className="space-y-3">
            {loading && <div className="text-ink-muted">Loading…</div>}
            {items.map((a) => {
              const Icon = ICONS[a.key] || Workflow;
              return (
                <div key={a.key} className="bg-bone-paper border border-edge rounded-md p-4 flex items-start gap-4" data-testid={`automation-${a.key}`}>
                  <div className="w-9 h-9 rounded-md bg-bone-subtle flex items-center justify-center">
                    <Icon className="w-4 h-4 text-walnut" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="font-medium text-ink text-sm">{a.name}</div>
                      <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-bone-subtle text-ink-muted">
                        runs today: {a.runs_today}
                      </span>
                    </div>
                    <div className="text-xs text-ink-soft mt-1">{a.description}</div>
                  </div>
                  <Toggle enabled={a.enabled} onChange={(v) => toggle(a.key, v)} testId={`toggle-${a.key}`} />
                </div>
              );
            })}
          </div>
        </section>

        <section className="col-span-12 lg:col-span-5">
          <h3 className="font-serif text-xl text-ink mb-3 flex items-center gap-2">
            <Radio className="w-4 h-4 text-clay" /> Live Signals
          </h3>
          <div className="bg-bone-paper border border-edge rounded-md p-4 max-h-[480px] overflow-y-auto scrollbar-thin">
            {signals.length === 0 && <div className="text-sm text-ink-muted italic">No automation events yet. Click "Run checks now" to evaluate.</div>}
            <div className="space-y-3">
              {signals.map((s) => (
                <div key={s.id} className="flex gap-3 text-sm">
                  <div className="font-mono text-[11px] text-ink-muted w-16 shrink-0 pt-0.5">{timeAgo(s.created_at)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-ink">{s.summary}</div>
                    <div className="text-[10px] uppercase tracking-wider text-clay">{s.event}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function GateCard({ title, rule, stages }) {
  return (
    <div className="bg-bone-paper border border-edge rounded-md p-4">
      <div className="flex items-center gap-1 mb-2">
        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: "#E2DCD0", color: "#5C534D" }}>S{stages[0]}</span>
        <span className="text-ink-muted">→</span>
        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: "#E2DCD0", color: "#5C534D" }}>S{stages[1]}</span>
      </div>
      <div className="font-medium text-sm text-ink">{title}</div>
      <div className="text-xs text-ink-soft mt-1">{rule}</div>
      <div className="mt-3 inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded text-stage-2 bg-stage-2/20">
        Active
      </div>
    </div>
  );
}

function Toggle({ enabled, onChange, testId }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      data-testid={testId}
      className={`relative w-10 h-6 rounded-full transition shrink-0 ${enabled ? "bg-clay" : "bg-bone-subtle border border-edge"}`}
    >
      <span
        className={`absolute top-0.5 ${enabled ? "left-5" : "left-0.5"} w-5 h-5 rounded-full bg-white shadow transition-all`}
      />
    </button>
  );
}

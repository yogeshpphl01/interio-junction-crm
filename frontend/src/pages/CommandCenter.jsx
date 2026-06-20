import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatINR, formatINRFull } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import { Toaster } from "sonner";
import {
  TrendingUp, Target, Trophy, Clock, Users2, IndianRupee,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, FunnelChart, Funnel, LabelList,
} from "recharts";
import { STAGES, LIFECYCLE_COLOR } from "@/lib/constants";

export default function CommandCenter() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/analytics/command-center")
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) return <div className="p-10 text-ink-muted">Loading…</div>;
  const { kpis } = data;

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6 max-w-7xl">
      <Toaster richColors position="top-right" />
      <div className="mb-6">
        <div className="flex items-baseline gap-3">
          <h2 className="font-serif text-3xl text-ink leading-none">
            Hello, <span className="italic">{user.full_name.split(" ")[0]}</span>
          </h2>
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">
            {data.scope === "company" ? "Company-wide view" : "Personal view"}
          </span>
        </div>
        <p className="text-ink-muted text-sm mt-2">
          Snapshot of pipeline health, forecast and on-floor activity.
        </p>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          title="Total Pipeline"
          value={formatINR(kpis.total_pipeline)}
          sub={formatINRFull(kpis.total_pipeline)}
          icon={IndianRupee}
          accent="#8A5A3B"
        />
        <KpiCard
          title="Forecast (probability-weighted)"
          value={formatINR(kpis.forecast)}
          sub="Σ budget × stage probability"
          icon={Target}
          accent="#C2683D"
        />
        <KpiCard title="Win Rate" value={`${kpis.win_rate}%`} sub={`${kpis.won_count} won`} icon={Trophy} accent="#8A9A5B" />
        <KpiCard title="Avg Cycle" value={`${kpis.cycle_days} d`} sub="from enquiry to close" icon={Clock} accent="#6B705C" />
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Forecast trend */}
        <div className="col-span-12 lg:col-span-8 bg-bone-paper border border-edge rounded-md p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-serif text-xl text-ink leading-none">Revenue Forecast</h3>
              <div className="text-xs text-ink-muted mt-1">Next 6 months · projected vs current pipeline</div>
            </div>
            <TrendingUp className="w-4 h-4 text-clay" />
          </div>
          <div className="h-64 min-h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.forecast_trend}>
                <defs>
                  <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#C2683D" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#C2683D" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="pipelineGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8A5A3B" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#8A5A3B" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#E2DCD0" strokeDasharray="3 3" />
                <XAxis dataKey="month" stroke="#8A817C" style={{ fontSize: 11 }} />
                <YAxis stroke="#8A817C" style={{ fontSize: 11 }} tickFormatter={(v) => v >= 1e7 ? `${(v/1e7).toFixed(1)}Cr` : v >= 1e5 ? `${(v/1e5).toFixed(0)}L` : v} />
                <Tooltip
                  contentStyle={{ background: "#FFFFFF", border: "1px solid #E2DCD0", borderRadius: 6, fontSize: 12 }}
                  formatter={(v) => formatINR(v)}
                />
                <Area type="monotone" dataKey="pipeline" stroke="#8A5A3B" strokeWidth={1.5} fill="url(#pipelineGrad)" name="Pipeline" />
                <Area type="monotone" dataKey="forecast" stroke="#C2683D" strokeWidth={2} fill="url(#forecastGrad)" name="Forecast" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Active leads */}
        <div className="col-span-12 lg:col-span-4 bg-bone-paper border border-edge rounded-md p-5 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-serif text-xl text-ink leading-none">Pipeline Funnel</h3>
            <Users2 className="w-4 h-4 text-clay" />
          </div>
          <div className="space-y-2 flex-1">
            {data.funnel.map((f) => {
              const max = Math.max(...data.funnel.map((x) => x.count || 0)) || 1;
              const pct = (f.count / max) * 100;
              return (
                <div key={f.stage} className="" data-testid={`funnel-${f.stage}`}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-ink-soft flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: f.color }} />
                      {f.name}
                    </span>
                    <span className="font-mono text-ink-muted">{f.count} · {formatINR(f.value)}</span>
                  </div>
                  <div className="h-2 rounded-full bg-bone-subtle overflow-hidden">
                    <div className="h-full" style={{ width: `${Math.max(pct, 4)}%`, background: f.color }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Source bar */}
        <div className="col-span-12 lg:col-span-7 bg-bone-paper border border-edge rounded-md p-5">
          <h3 className="font-serif text-xl text-ink leading-none mb-3">Pipeline Value by Source</h3>
          <div className="h-64 min-h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.by_source} layout="vertical" margin={{ left: 30 }}>
                <CartesianGrid stroke="#E2DCD0" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#8A817C" style={{ fontSize: 11 }} tickFormatter={(v) => v >= 1e7 ? `${(v/1e7).toFixed(1)}Cr` : v >= 1e5 ? `${(v/1e5).toFixed(0)}L` : v} />
                <YAxis type="category" dataKey="source" stroke="#8A817C" style={{ fontSize: 11 }} width={110} />
                <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E2DCD0", borderRadius: 6, fontSize: 12 }} formatter={(v) => formatINR(v)} />
                <Bar dataKey="value" fill="#9C6644" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Stage counts grid */}
        <div className="col-span-12 lg:col-span-5 bg-bone-paper border border-edge rounded-md p-5">
          <h3 className="font-serif text-xl text-ink leading-none mb-3">Stage Probability Reference</h3>
          <div className="space-y-2">
            {STAGES.map((s, i) => {
              const win = [10, 25, 45, 65, 85, 100][i];
              return (
                <div key={s.id} className="flex items-center justify-between text-sm py-1.5 border-b border-edge last:border-0">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
                    <span className="text-ink">{s.short}</span>
                  </div>
                  <span className="font-mono text-ink-soft">{win}%</span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3 border-t border-edge text-[11px] text-ink-muted leading-relaxed">
            Forecast = Σ (lead.budget × stage probability). Conservative — reflects how late-stage leads have higher likelihood of close.
          </div>
        </div>

        {/* NEW: Lead journey distribution across lifecycle buckets */}
        <div className="col-span-12 lg:col-span-6 bg-bone-paper border border-edge rounded-md p-5">
          <h3 className="font-serif text-xl text-ink leading-none mb-3">Lead Journey Distribution</h3>
          <div className="space-y-2">
            {(data.by_lifecycle || []).map((p) => {
              const max = Math.max(...(data.by_lifecycle || []).map((x) => x.count || 0)) || 1;
              const pct = (p.count / max) * 100;
              const color = LIFECYCLE_COLOR[p.phase] || "#8A817C";
              return (
                <div key={p.phase} data-testid={`lifecycle-bar-${p.phase}`}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-ink-soft flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
                      {p.phase}
                    </span>
                    <span className="font-mono text-ink-muted">{p.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-bone-subtle overflow-hidden">
                    <div className="h-full" style={{ width: `${Math.max(pct, 4)}%`, background: color }} />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3 border-t border-edge text-[11px] text-ink-muted leading-relaxed">
            Where leads sit in their journey: only enquired, mid-pipeline, completed (delivered), dropped, or on-hold.
          </div>
        </div>

        {/* NEW: Drop-off by stage — where Lost/Dropped leads stopped proceeding */}
        <div className="col-span-12 lg:col-span-6 bg-bone-paper border border-edge rounded-md p-5">
          <h3 className="font-serif text-xl text-ink leading-none mb-3">Drop-off by Stage</h3>
          <div className="space-y-2">
            {(data.dropoff_by_stage || []).map((s) => {
              const max = Math.max(...(data.dropoff_by_stage || []).map((x) => x.count || 0)) || 1;
              const pct = (s.count / max) * 100;
              return (
                <div key={s.stage} data-testid={`dropoff-${s.stage}`}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-ink-soft flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
                      {s.name}
                    </span>
                    <span className="font-mono text-ink-muted">{s.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-bone-subtle overflow-hidden">
                    <div className="h-full" style={{ width: `${Math.max(pct, 4)}%`, background: s.color }} />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3 border-t border-edge text-[11px] text-ink-muted leading-relaxed">
            Stage at which leads stopped proceeding. Heavy early-stage drop-off suggests qualifying or nurturing sooner.
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value, sub, icon: Icon, accent }) {
  return (
    <div className="bg-bone-paper border border-edge rounded-md p-5 flex flex-col" data-testid={`kpi-${title.replace(/\s+/g, "-").toLowerCase()}`}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.16em] text-ink-muted font-semibold">{title}</div>
        <div className="w-8 h-8 rounded-md flex items-center justify-center" style={{ background: `${accent}1A`, color: accent }}>
          {Icon && <Icon className="w-4 h-4" />}
        </div>
      </div>
      <div className="font-serif text-4xl text-ink mt-3 leading-none">{value}</div>
      <div className="text-[11px] text-ink-muted mt-2">{sub}</div>
    </div>
  );
}

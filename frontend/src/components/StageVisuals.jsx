import { STAGES } from "@/lib/constants";

export function StageDot({ stage, size = 8 }) {
  const s = STAGES.find((x) => x.id === stage);
  return (
    <span
      className="inline-block rounded-full"
      style={{ background: s?.color || "#8A817C", width: size, height: size }}
    />
  );
}

export function StageBadge({ stage }) {
  const s = STAGES.find((x) => x.id === stage);
  if (!s) return null;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium"
      style={{
        backgroundColor: `${s.color}22`,
        color: s.color,
        border: `1px solid ${s.color}33`,
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
      {s.short}
    </span>
  );
}

export function HeatChip({ heat, score }) {
  const map = {
    Hot: { bg: "#C2683D22", color: "#C2683D", border: "#C2683D44" },
    Warm: { bg: "#D4A37322", color: "#A56A2E", border: "#D4A37344" },
    Cold: { bg: "#6B705C22", color: "#6B705C", border: "#6B705C44" },
  };
  const c = map[heat] || map.Cold;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide"
      style={{ backgroundColor: c.bg, color: c.color, border: `1px solid ${c.border}` }}
      data-testid={`heat-chip-${heat?.toLowerCase()}`}
    >
      {heat}
      {score != null && <span className="font-mono">· {score}</span>}
    </span>
  );
}

export function Stepper({ current }) {
  return (
    <div className="flex items-center justify-between w-full gap-1" data-testid="stage-stepper">
      {STAGES.map((s, idx) => {
        const done = s.id < current;
        const active = s.id === current;
        const bg = done ? "#8A9A5B" : active ? s.color : "#EBE5D9";
        const fg = done || active ? "#FFFFFF" : "#8A817C";
        return (
          <div key={s.id} className="flex-1 flex items-center gap-1">
            <div className="flex flex-col items-center min-w-0 flex-1">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center font-mono text-[11px] font-bold"
                style={{ background: bg, color: fg }}
              >
                {done ? "✓" : s.id}
              </div>
              <div className="mt-1.5 text-[10px] uppercase tracking-wide text-ink-muted text-center leading-tight">
                {s.short}
              </div>
            </div>
            {idx < STAGES.length - 1 && (
              <div className="flex-1 h-px" style={{ background: s.id < current ? "#8A9A5B" : "#E2DCD0" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

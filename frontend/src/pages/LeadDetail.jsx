import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { api, API_BASE } from "@/lib/api";
import { Stepper, StageBadge, HeatChip, StageDot, LifecycleBadge } from "@/components/StageVisuals";
import { formatINR, formatINRFull, fmtDate, initials, timeAgo } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import { toast, Toaster } from "sonner";
import {
  ArrowLeft, FileText, Image as ImageIcon, Upload, Download,
  Plus, Pencil, Phone, Mail, MapPin, Calendar, Ruler, Layers, IndianRupee,
  Trophy, XCircle, PauseCircle, RotateCcw, Footprints,
} from "lucide-react";
import CloseLeadModal from "@/components/CloseLeadModal";

export default function LeadDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState("");
  const [closing, setClosing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/leads/${id}`);
      setData(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading || !data) return <div className="p-10 text-ink-muted">Loading…</div>;

  const isAdminOrSales = user.role === "admin" || user.role === "sales";
  const isDesigner = user.role === "designer";
  const isSupervisor = user.role === "supervisor";

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6 max-w-7xl">
      <Toaster richColors position="top-right" />
      <Link
        to="/pipeline"
        data-testid="back-to-pipeline"
        className="inline-flex items-center gap-1 text-ink-muted hover:text-ink text-sm mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> Back to Pipeline
      </Link>

      <div className="bg-bone-paper border border-edge rounded-md p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <StageBadge stage={data.stage} />
              <HeatChip heat={data.heat} score={data.score} />
              {data.project?.project_code && (
                <span className="font-mono text-[11px] text-ink-soft bg-bone-subtle border border-edge rounded px-1.5 py-0.5">
                  {data.project.project_code}
                </span>
              )}
            </div>
            <h2 className="font-serif text-3xl text-ink leading-tight" data-testid="lead-title">
              {data.full_name}
            </h2>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-sm text-ink-soft">
              {data.phone && (
                <span className="inline-flex items-center gap-1.5"><Phone className="w-3.5 h-3.5" /> {data.phone}</span>
              )}
              {data.email && (
                <span className="inline-flex items-center gap-1.5"><Mail className="w-3.5 h-3.5" /> {data.email}</span>
              )}
              {(data.city || data.address) && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5" /> {[data.address, data.city].filter(Boolean).join(", ")}
                </span>
              )}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">Tentative budget</div>
            <div className="font-serif text-3xl text-ink">{formatINR(data.tentative_budget)}</div>
            <div className="text-xs text-ink-muted mt-0.5">{formatINRFull(data.tentative_budget)}</div>
            {isAdminOrSales && (
              <div className="mt-3 flex justify-end">
                <CloseStatusButton lead={data} onOpen={() => setClosing(true)} />
              </div>
            )}
          </div>
        </div>

        {(data.status === "Won" || data.status === "Lost" || data.status === "On-hold") && (
          <ClosedBanner lead={data} />
        )}

        {/* NEW: journey lifecycle summary above the stage stepper */}
        <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2">
          <LifecycleBadge phase={data.lifecycle_phase} />
          <span className="text-xs text-ink-muted">
            Furthest stage reached:{" "}
            <span className="text-ink-soft font-medium">{data.furthest_stage || data.stage}</span> / 6
          </span>
          {data.dropped_stage && (
            <span className="text-xs text-[#A95A3F]">
              Dropped at stage {data.dropped_stage}
              {data.dropped_reason ? ` — ${data.dropped_reason}` : ""}
            </span>
          )}
          {data.delivered_at && (
            <span className="text-xs text-[#4A5D23]">Delivered {fmtDate(data.delivered_at)}</span>
          )}
        </div>
        <div className="mt-4 pt-2">
          <Stepper current={data.stage} />
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6 mt-6">
        <div className="col-span-12 lg:col-span-8 space-y-6">
          {/* Brief */}
          <Card title="Requirement Brief" icon={FileText}>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <MetaCell label="Lead Type" value={data.lead_type} />
              <MetaCell label="Source" value={data.source} />
              <MetaCell label="BHK" value={data.bhk_type} />
              <MetaCell label="Kitchen Layout" value={data.kitchen_layout} />
              <MetaCell label="Status" value={data.status} />
              <MetaCell label="Owner" value={data.owner?.full_name || "—"} />
            </div>
            {data.requirements && (
              <p className="mt-4 text-sm text-ink leading-relaxed border-l-2 border-clay/50 pl-4 italic">
                {data.requirements}
              </p>
            )}
          </Card>

          {/* Site Measurements */}
          <Card
            title="Site Measurements"
            icon={Ruler}
            action={
              data.project && (isAdminOrSales || isSupervisor) ? (
                <button
                  data-testid="add-measurement-btn"
                  onClick={() => setAdding("measurement")}
                  className="inline-flex items-center gap-1 text-xs text-clay hover:text-clay-deep"
                >
                  <Plus className="w-3.5 h-3.5" /> Add
                </button>
              ) : null
            }
          >
            {data.measurements.length === 0 ? (
              <Empty text="No site measurements yet." />
            ) : (
              <div className="space-y-3">
                {data.measurements.map((m) => (
                  <MeasurementRow key={m.id} m={m} onChange={load} canEdit={isAdminOrSales || (isSupervisor && m.supervisor_id === user.id)} project={data.project} />
                ))}
              </div>
            )}
          </Card>

          {/* Design Revisions */}
          <Card
            title="Design Revisions"
            icon={Layers}
            action={
              data.project && (isAdminOrSales || isDesigner) ? (
                <button
                  data-testid="add-revision-btn"
                  onClick={() => setAdding("revision")}
                  className="inline-flex items-center gap-1 text-xs text-clay hover:text-clay-deep"
                >
                  <Plus className="w-3.5 h-3.5" /> Add R{(data.revisions?.length || 0) + 1}
                </button>
              ) : null
            }
          >
            {data.revisions.length === 0 ? (
              <Empty text="No revisions yet." />
            ) : (
              <div className="space-y-3">
                {data.revisions.map((r) => (
                  <RevisionRow key={r.id} r={r} onChange={load} canEdit={isAdminOrSales || (isDesigner && r.designer_id === user.id)} project={data.project} />
                ))}
              </div>
            )}
          </Card>

          {/* Documents */}
          <Card title="Documents" icon={ImageIcon}>
            {data.documents.length === 0 ? (
              <Empty text="No files uploaded yet." />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {data.documents.map((d) => (
                  <DocumentRow key={d.id} doc={d} />
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-6">
          {/* Payments rail */}
          <Card title="Milestone Payments" icon={IndianRupee}>
            {data.payments.length === 0 ? (
              <Empty text="No payments configured yet." />
            ) : (
              <div className="space-y-2">
                {data.payments.map((p) => (
                  <PaymentRow key={p.id} p={p} onChange={load} canEdit={isAdminOrSales} />
                ))}
                <PaymentSummary payments={data.payments} />
              </div>
            )}
          </Card>

          {/* NEW: Lead journey — per-stage entry/exit timeline */}
          <Card title="Lead Journey" icon={Footprints}>
            <JourneyTimeline journey={data.journey} />
          </Card>

          {/* Activity timeline */}
          <Card title="Stage Activity" icon={Calendar}>
            <Timeline activities={data.activities} history={data.stage_history} />
            <AddActivity leadId={data.id} onAdded={load} />
          </Card>
        </div>
      </div>

      {adding === "measurement" && (
        <MeasurementModal
          projectId={data.project?.id}
          onClose={() => setAdding("")}
          onSaved={() => {
            setAdding("");
            load();
          }}
        />
      )}
      {adding === "revision" && (
        <RevisionModal
          projectId={data.project?.id}
          onClose={() => setAdding("")}
          onSaved={() => {
            setAdding("");
            load();
          }}
        />
      )}
      {closing && (
        <CloseLeadModal
          lead={data}
          onClose={() => setClosing(false)}
          onClosed={() => {
            setClosing(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function CloseStatusButton({ lead, onOpen }) {
  const isActive = lead.status === "Active";
  return (
    <button
      onClick={onOpen}
      data-testid="close-lead-btn"
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border transition ${
        isActive
          ? "border-edge text-ink hover:bg-bone-subtle"
          : "border-clay/40 text-clay hover:bg-clay/5"
      }`}
    >
      {isActive ? (
        <>
          <Trophy className="w-3.5 h-3.5" /> Close lead…
        </>
      ) : (
        <>
          <RotateCcw className="w-3.5 h-3.5" /> Reopen lead
        </>
      )}
    </button>
  );
}

function ClosedBanner({ lead }) {
  const map = {
    Won: { icon: Trophy, color: "#4A5D23", bg: "#4A5D2310", label: "Won" },
    Lost: { icon: XCircle, color: "#A95A3F", bg: "#A95A3F10", label: "Lost" },
    "On-hold": { icon: PauseCircle, color: "#8A817C", bg: "#8A817C10", label: "On hold" },
  };
  const s = map[lead.status];
  if (!s) return null;
  const Icon = s.icon;
  const reason = lead.lost_reason || lead.won_reason || lead.hold_reason;
  return (
    <div
      className="mt-4 rounded-md border px-4 py-3 flex items-start gap-3"
      style={{ borderColor: `${s.color}33`, background: s.bg }}
      data-testid="closed-banner"
    >
      <Icon className="w-4 h-4 mt-0.5 shrink-0" style={{ color: s.color }} />
      <div className="min-w-0">
        <div className="text-sm font-semibold" style={{ color: s.color }}>
          Lead marked {s.label}
          {lead.won_value ? ` · ${formatINR(lead.won_value)} contract` : ""}
        </div>
        {reason && <div className="text-xs text-ink-soft mt-0.5 italic">{reason}</div>}
      </div>
    </div>
  );
}

function Card({ title, icon: Icon, action, children }) {
  return (
    <section className="bg-bone-paper border border-edge rounded-md">
      <header className="px-5 py-3 border-b border-edge flex items-center justify-between">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 text-ink-soft" strokeWidth={1.75} />}
          <h3 className="font-serif text-base text-ink">{title}</h3>
        </div>
        {action}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function MetaCell({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink-muted font-semibold">{label}</div>
      <div className="text-sm text-ink mt-0.5">{value || "—"}</div>
    </div>
  );
}

function Empty({ text }) {
  return <div className="text-sm text-ink-muted italic py-2">{text}</div>;
}

function MeasurementRow({ m, canEdit, onChange, project }) {
  const statusColor = {
    Completed: "#8A9A5B",
    "In Progress": "#D4A373",
    Scheduled: "#6B705C",
  }[m.status] || "#8A817C";
  const [editing, setEditing] = useState(false);

  const mark = async (status) => {
    try {
      await api.patch(`/measurements/${m.id}`, {
        status,
        completed_at: status === "Completed" ? new Date().toISOString() : null,
      });
      toast.success(`Status: ${status}`);
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    }
  };

  return (
    <div className="border border-edge rounded-md p-3 bg-bone">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-ink">
            {fmtDate(m.scheduled_at, true)}
            <span className="ml-2 text-[11px] font-mono px-1.5 py-0.5 rounded" style={{ background: `${statusColor}22`, color: statusColor }}>
              {m.status}
            </span>
          </div>
          <div className="text-xs text-ink-muted mt-1">
            Supervisor: <span className="text-ink-soft">{m.supervisor?.full_name || "—"}</span>
          </div>
        </div>
        {canEdit && m.status !== "Completed" && (
          <button data-testid={`measurement-complete-${m.id}`} onClick={() => mark("Completed")} className="text-xs text-clay hover:text-clay-deep underline">
            Mark complete
          </button>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
        <Kv label="Area" v={m.total_area_sqft ? `${m.total_area_sqft} sqft` : "—"} />
        <Kv label="Ceiling" v={m.ceiling_height ? `${m.ceiling_height} ft` : "—"} />
        <Kv label="Completed" v={m.completed_at ? fmtDate(m.completed_at) : "—"} />
      </div>
      {m.notes && <div className="mt-2 text-xs text-ink-soft italic">{m.notes}</div>}
      {canEdit && project && (
        <UploadButton project={project} type="Site Measurement Sheet" linkedMeasurementId={m.id} onUploaded={onChange} />
      )}
    </div>
  );
}

function RevisionRow({ r, canEdit, onChange, project }) {
  const STATUSES = ["Draft", "Shared", "Revision Requested", "Approved", "Rejected"];
  const statusColor = {
    Approved: "#8A9A5B",
    Shared: "#9C6644",
    Draft: "#8A817C",
    "Revision Requested": "#C2683D",
    Rejected: "#A95A3F",
  }[r.status] || "#8A817C";
  const updateStatus = async (status) => {
    try {
      await api.patch(`/revisions/${r.id}`, { status });
      toast.success(`Revision ${status}`);
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    }
  };

  return (
    <div className="border border-edge rounded-md p-3 bg-bone">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-ink">
            R{r.revision_number} · {r.title}
            <span className="ml-2 text-[11px] font-mono px-1.5 py-0.5 rounded" style={{ background: `${statusColor}22`, color: statusColor }}>
              {r.status}
            </span>
          </div>
          <div className="text-xs text-ink-muted mt-1">
            Designer: <span className="text-ink-soft">{r.designer?.full_name || "—"}</span> · {timeAgo(r.created_at)}
          </div>
        </div>
        {canEdit && (
          <select
            data-testid={`revision-status-${r.id}`}
            value={r.status}
            onChange={(e) => updateStatus(e.target.value)}
            className="text-xs bg-bone-paper border border-edge rounded px-1.5 py-1"
          >
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        )}
      </div>
      {r.client_feedback && (
        <div className="text-xs text-ink-soft italic mt-2 border-l-2 border-bone-deep pl-3">{r.client_feedback}</div>
      )}
      {canEdit && project && (
        <UploadButton project={project} type="2D CAD" linkedRevisionId={r.id} onUploaded={onChange} />
      )}
    </div>
  );
}

function PaymentRow({ p, canEdit, onChange }) {
  const colors = {
    Paid: "#8A9A5B",
    Pending: "#8A817C",
    Partial: "#D4A373",
    Overdue: "#A95A3F",
  };
  const c = colors[p.status] || "#8A817C";
  const togglePaid = async () => {
    try {
      const newStatus = p.status === "Paid" ? "Pending" : "Paid";
      await api.patch(`/payments/${p.id}`, { status: newStatus });
      toast.success(newStatus === "Paid" ? "Payment received" : "Marked pending");
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    }
  };
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-edge last:border-0">
      <div className="min-w-0">
        <div className="text-sm text-ink truncate">{p.milestone}</div>
        <div className="text-[11px] text-ink-muted">Due {fmtDate(p.due_date)}</div>
      </div>
      <div className="text-right shrink-0 ml-3">
        <div className="text-sm font-mono text-ink">{formatINR(p.amount)}</div>
        <button
          data-testid={`payment-toggle-${p.id}`}
          disabled={!canEdit}
          onClick={togglePaid}
          className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
          style={{ background: `${c}22`, color: c, opacity: canEdit ? 1 : 0.7 }}
        >
          {p.status}
        </button>
      </div>
    </div>
  );
}

function PaymentSummary({ payments }) {
  const total = payments.reduce((a, b) => a + b.amount, 0);
  const paid = payments.filter((p) => p.status === "Paid").reduce((a, b) => a + b.amount, 0);
  const pct = total ? Math.round((paid / total) * 100) : 0;
  return (
    <div className="mt-3 pt-3 border-t border-edge">
      <div className="flex justify-between text-xs text-ink-soft mb-1">
        <span>{formatINR(paid)} collected</span>
        <span>{pct}% of {formatINR(total)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-bone-subtle overflow-hidden">
        <div className="h-full bg-stage-2" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DocumentRow({ doc }) {
  const onDownload = async () => {
    try {
      const res = await api.get(`/documents/${doc.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.original_filename || "file";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Download failed");
    }
  };
  return (
    <button
      onClick={onDownload}
      data-testid={`doc-download-${doc.id}`}
      className="flex items-center justify-between gap-2 border border-edge rounded-md px-3 py-2 hover:border-clay/40 hover:bg-bone text-left"
    >
      <div className="min-w-0">
        <div className="text-sm text-ink truncate">{doc.original_filename || "file"}</div>
        <div className="text-[11px] text-ink-muted">{doc.type} · {timeAgo(doc.created_at)}</div>
      </div>
      <Download className="w-4 h-4 text-ink-muted shrink-0" />
    </button>
  );
}

function UploadButton({ project, type, linkedMeasurementId, linkedRevisionId, onUploaded }) {
  const [busy, setBusy] = useState(false);
  const onPick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("project_id", project.id);
    fd.append("type", type);
    if (linkedMeasurementId) fd.append("linked_measurement_id", linkedMeasurementId);
    if (linkedRevisionId) fd.append("linked_revision_id", linkedRevisionId);
    fd.append("file", file);
    try {
      await api.post("/documents", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Uploaded");
      onUploaded();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };
  return (
    <label className="mt-3 inline-flex items-center gap-1 text-xs text-clay hover:text-clay-deep cursor-pointer">
      <Upload className="w-3.5 h-3.5" />
      <span>{busy ? "Uploading…" : `Attach ${type}`}</span>
      <input type="file" className="hidden" onChange={onPick} data-testid={`upload-${type.replace(/\s+/g, "-").toLowerCase()}`} />
    </label>
  );
}

function Kv({ label, v }) {
  return (
    <div className="bg-bone-paper rounded border border-edge px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="text-xs text-ink font-medium mt-0.5">{v}</div>
    </div>
  );
}

/*
  <component name="JourneyTimeline">
    Renders the per-stage journey (entered_at/exited_at per stage) captured in
    the lead's `journey` JSONB. The last open stage is the lead's current step.
  </component>
*/
function JourneyTimeline({ journey }) {
  if (!journey || journey.length === 0) return <Empty text="No journey recorded yet." />;
  return (
    <ol className="space-y-3" data-testid="journey-timeline">
      {journey.map((j, i) => (
        <li key={i} className="flex items-start gap-3">
          <StageDot stage={j.stage} size={10} />
          <div className="min-w-0">
            <div className="text-sm text-ink">{j.stage_name || `Stage ${j.stage}`}</div>
            <div className="text-[11px] text-ink-muted">
              Entered {fmtDate(j.entered_at, true)}
              {j.exited_at ? ` · Exited ${fmtDate(j.exited_at, true)}` : " · current step"}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Timeline({ activities, history }) {
  const items = [...activities].sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
  if (!items.length) return <Empty text="No activity yet." />;
  return (
    <div className="space-y-3">
      {items.slice(0, 20).map((a) => (
        <div key={a.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="w-2 h-2 rounded-full bg-clay mt-1.5" />
            <div className="flex-1 w-px bg-edge" />
          </div>
          <div className="flex-1 pb-3">
            <div className="text-sm text-ink">{a.summary}</div>
            <div className="text-[11px] text-ink-muted mt-0.5">
              {a.type} · {a.actor?.full_name || "system"} · {timeAgo(a.created_at)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function AddActivity({ leadId, onAdded }) {
  const [text, setText] = useState("");
  const [type, setType] = useState("Note");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.post("/activities", { lead_id: leadId, type, summary: text.trim() });
      setText("");
      onAdded();
    } catch (e) {
      toast.error("Could not add");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-3 pt-3 border-t border-edge space-y-2">
      <div className="flex gap-2">
        <select value={type} onChange={(e) => setType(e.target.value)} className="text-xs bg-bone-paper border border-edge rounded px-2 py-1" data-testid="activity-type">
          {["Note", "Call", "Email", "Meeting"].map((t) => <option key={t}>{t}</option>)}
        </select>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Log activity…"
          className="flex-1 text-sm bg-bone-paper border border-edge rounded px-2 py-1 focus:border-clay outline-none"
          data-testid="activity-text"
        />
        <button onClick={submit} disabled={busy || !text.trim()} className="text-xs bg-clay text-white rounded px-3 py-1 disabled:opacity-50" data-testid="activity-add-btn">
          Add
        </button>
      </div>
    </div>
  );
}

function MeasurementModal({ projectId, onClose, onSaved }) {
  const [form, setForm] = useState({
    project_id: projectId,
    scheduled_at: new Date().toISOString().slice(0, 16),
    supervisor_id: "",
    status: "Scheduled",
    notes: "",
  });
  const [supervisors, setSupervisors] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/users").then((r) => setSupervisors(r.data.filter((u) => u.role === "supervisor")));
  }, []);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/measurements", form);
      toast.success("Measurement scheduled");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal onClose={onClose} title="New Site Measurement">
      <form onSubmit={submit} className="space-y-3">
        <FieldM label="Scheduled at"><input type="datetime-local" required value={form.scheduled_at} onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })} className={inputCls} /></FieldM>
        <FieldM label="Supervisor">
          <select value={form.supervisor_id} onChange={(e) => setForm({ ...form, supervisor_id: e.target.value })} className={inputCls}>
            <option value="">— select —</option>
            {supervisors.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
          </select>
        </FieldM>
        <FieldM label="Notes"><textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3} className={inputCls} /></FieldM>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
          <button disabled={busy} type="submit" data-testid="submit-measurement" className="bg-clay text-white px-3 py-1.5 text-sm rounded disabled:opacity-50">
            {busy ? "Saving…" : "Schedule"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function RevisionModal({ projectId, onClose, onSaved }) {
  const [form, setForm] = useState({ project_id: projectId, title: "", designer_id: "", status: "Draft" });
  const [designers, setDesigners] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/users").then((r) => setDesigners(r.data.filter((u) => u.role === "designer")));
  }, []);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/revisions", form);
      toast.success("Revision created");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal onClose={onClose} title="New Design Revision">
      <form onSubmit={submit} className="space-y-3">
        <FieldM label="Title"><input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={inputCls} placeholder="e.g. Initial 3D Concept" /></FieldM>
        <FieldM label="Designer">
          <select value={form.designer_id} onChange={(e) => setForm({ ...form, designer_id: e.target.value })} className={inputCls}>
            <option value="">— select —</option>
            {designers.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
          </select>
        </FieldM>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-ink-soft">Cancel</button>
          <button disabled={busy} type="submit" data-testid="submit-revision" className="bg-clay text-white px-3 py-1.5 text-sm rounded disabled:opacity-50">
            {busy ? "Saving…" : "Create"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-bone-paper border border-edge rounded-md w-full max-w-md">
        <div className="px-5 py-4 border-b border-edge flex justify-between">
          <h3 className="font-serif text-xl text-ink">{title}</h3>
          <button onClick={onClose} className="text-ink-soft hover:text-ink text-2xl leading-none">×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function FieldM({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputCls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay focus:ring-2 focus:ring-clay/20 outline-none";

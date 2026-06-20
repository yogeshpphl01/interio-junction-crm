/*
  <page name="NotificationSettings" route="/notifications" access="admin">
    <purpose>Configure email alerts: master switch, admin recipient and per-event
    toggles (GET/POST /notifications/settings), plus a rate-limited test send
    (POST /notifications/test).</purpose>
  </page>
*/
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { Mail, CheckCircle2, AlertTriangle, Send, Save } from "lucide-react";

const EVENT_LABELS = {
  sla_breach_48h: "SLA breach (48h idle)",
  escalate_hot_lead: "Hot lead untouched (24h)",
  notify_designer_revision: "Designer · Revision Requested",
};

export default function NotificationSettings() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api.get("/notifications/settings").then((r) => {
      setCfg(r.data);
      setTestTo(r.data.admin_email || "");
    });
  }, []);

  if (!cfg) return <div className="p-10 text-ink-muted">Loading…</div>;

  const setField = (k, v) => setCfg((p) => ({ ...p, [k]: v }));
  const setEvent = (k, v) => setCfg((p) => ({ ...p, events: { ...p.events, [k]: v } }));

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/notifications/settings", {
        enabled: !!cfg.enabled,
        admin_email: cfg.admin_email || null,
        from_email: cfg.from_email || null,
        events: cfg.events,
      });
      setCfg(data);
      toast.success("Notification settings saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    if (!testTo) return toast.error("Enter a recipient");
    setTesting(true);
    try {
      const { data } = await api.post("/notifications/test", { to: testTo });
      if (data.ok) toast.success("Test email sent — check your inbox");
      else toast.error(`Send failed: ${data.info}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-10 py-6 max-w-4xl">
      <Toaster richColors position="top-right" />
      <div className="mb-6">
        <h2 className="font-serif text-3xl text-ink leading-none">Notifications</h2>
        <p className="text-ink-muted text-sm mt-2 max-w-xl">
          Email alerts for SLA breaches, Hot lead escalations and design revision requests.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Provider */}
        <div className="bg-bone-paper border border-edge rounded-md p-5">
          <h3 className="font-serif text-lg text-ink mb-3 flex items-center gap-2">
            <Mail className="w-4 h-4 text-clay" /> Provider
          </h3>
          <div className="space-y-3 text-sm">
            <KV label="Method" value="SMTP" />
            <KV label="Host" value={cfg.smtp_host || "—"} />
            <KV label="Mailbox" value={cfg.smtp_user || "—"} />
            <KV label="From address" value={cfg.from_email || "—"} />
            <div className="flex items-center gap-2 pt-2 mt-2 border-t border-edge">
              {cfg.configured ? (
                <span className="inline-flex items-center gap-1 text-xs text-stage-2">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Credentials present
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs text-clay-deep">
                  <AlertTriangle className="w-3.5 h-3.5" /> Not configured · add SMTP vars to backend .env
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Master toggle + recipients */}
        <div className="bg-bone-paper border border-edge rounded-md p-5">
          <h3 className="font-serif text-lg text-ink mb-3">Routing</h3>
          <div className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm text-ink">Enable email notifications</div>
              <div className="text-[11px] text-ink-muted">Master switch. Off = no emails are sent.</div>
            </div>
            <Toggle enabled={!!cfg.enabled} onChange={(v) => setField("enabled", v)} testId="toggle-enabled" />
          </div>
          <div className="mt-3">
            <Label>Admin email</Label>
            <input
              data-testid="admin-email"
              value={cfg.admin_email || ""}
              onChange={(e) => setField("admin_email", e.target.value)}
              placeholder="admin@yourdomain.com"
              className={cls}
            />
            <div className="text-[11px] text-ink-muted mt-1">Always copied on alerts (in addition to the assigned owner).</div>
          </div>
        </div>

        {/* Per-event toggles */}
        <div className="bg-bone-paper border border-edge rounded-md p-5 lg:col-span-2">
          <h3 className="font-serif text-lg text-ink mb-3">Events</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {Object.keys(EVENT_LABELS).map((k) => (
              <div key={k} className="flex items-start justify-between gap-3 border border-edge rounded-md p-3 bg-bone">
                <div className="min-w-0">
                  <div className="text-sm text-ink">{EVENT_LABELS[k]}</div>
                  <div className="text-[11px] text-ink-muted font-mono">{k}</div>
                </div>
                <Toggle enabled={cfg.events?.[k] !== false} onChange={(v) => setEvent(k, v)} testId={`event-${k}`} />
              </div>
            ))}
          </div>
        </div>

        {/* Save + test */}
        <div className="bg-bone-paper border border-edge rounded-md p-5 lg:col-span-2 flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-2">
            <input
              data-testid="test-to-input"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder="recipient@example.com"
              className={cls + " w-64"}
            />
            <button
              onClick={sendTest}
              disabled={testing || !cfg.configured}
              data-testid="send-test-btn"
              className="inline-flex items-center gap-1 px-3 py-2 text-sm border border-edge rounded-md text-ink hover:bg-bone-subtle disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" /> {testing ? "Sending…" : "Send test"}
            </button>
          </div>
          <button
            onClick={save}
            disabled={saving}
            data-testid="save-notifications-btn"
            className="inline-flex items-center gap-1 px-3 py-2 text-sm bg-clay text-white rounded-md disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function KV({ label, value }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-ink-muted text-xs">{label}</span>
      <span className="font-mono text-ink text-xs truncate max-w-[60%] text-right">{value}</span>
    </div>
  );
}
function Label({ children }) {
  return <span className="text-[11px] uppercase tracking-wide text-ink-soft font-semibold">{children}</span>;
}
function Toggle({ enabled, onChange, testId }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      data-testid={testId}
      className={`relative w-10 h-6 rounded-full transition shrink-0 ${enabled ? "bg-clay" : "bg-bone-subtle border border-edge"}`}
    >
      <span className={`absolute top-0.5 ${enabled ? "left-5" : "left-0.5"} w-5 h-5 rounded-full bg-white shadow transition-all`} />
    </button>
  );
}
const cls = "w-full bg-bone-paper border border-edge rounded-md px-3 py-2 text-ink text-sm focus:border-clay outline-none";

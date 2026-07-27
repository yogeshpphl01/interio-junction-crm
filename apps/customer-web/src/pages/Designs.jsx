/*
  Designs — the customer's shared design revisions with attached renders/CAD.
  Two feedback actions per shared design:
    • Approve            POST /client/designs/{id}/approve
    • Request changes    POST /client/designs/{id}/request-changes { feedback }
  Approve is a high-risk action, so it routes through postWithStepUp.
*/
import { useState } from "react";
import { PenTool, CheckCircle2, MessageSquarePlus, Download, X } from "lucide-react";
import { api, apiError, assetUrl, postWithStepUp } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardBody, Empty, PageLoader } from "@/components/ui";
import { shortDate } from "@/lib/format";

const STATUS = {
  Shared: { tone: "amber", label: "Awaiting your review" },
  Approved: { tone: "green", label: "Approved" },
  "Revision Requested": { tone: "blue", label: "Changes requested" },
};

function RequestChangesDialog({ design, onClose, onDone }) {
  const { push } = useToast();
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await api.post(`/client/designs/${design.id}/request-changes`, { feedback });
      push({ title: "Feedback sent", description: "Our design team has been notified.", tone: "success" });
      onDone();
    } catch (e) {
      push({ title: "Couldn't send feedback", description: apiError(e), tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Request changes</h3>
            <p className="mt-0.5 text-sm text-slate-500">Design R{design.revision_number}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        <textarea
          className="mt-4 h-32 w-full resize-none rounded-xl border border-slate-200 p-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
          placeholder="Tell us what you'd like changed — layout, materials, colours, dimensions…"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          autoFocus
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={busy} disabled={!feedback.trim()}>Send feedback</Button>
        </div>
      </div>
    </div>
  );
}

export default function Designs() {
  const { data, loading, error, reload } = useApi("/client/designs");
  const { push } = useToast();
  const [approving, setApproving] = useState(null);
  const [dialog, setDialog] = useState(null);

  const designs = data?.designs || [];

  async function approve(design) {
    setApproving(design.id);
    try {
      await postWithStepUp(`/client/designs/${design.id}/approve`);
      push({ title: "Design approved", description: `R${design.revision_number} is approved — this unlocks production.`, tone: "success" });
      await reload();
    } catch (e) {
      push({ title: "Couldn't approve", description: apiError(e), tone: "error" });
    } finally {
      setApproving(null);
    }
  }

  async function download(doc) {
    try {
      const { data } = await api.get(`/client/documents/${doc.id}/signed-url`);
      window.open(assetUrl(data.url), "_blank", "noopener");
    } catch (e) {
      push({ title: "Couldn't open file", description: apiError(e), tone: "error" });
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Designs</h1>
        <p className="mt-1 text-slate-500">Review your 3D renders and drawings, then approve or ask for changes.</p>
      </div>

      {error ? (
        <Empty icon={PenTool} title="Couldn't load designs" hint={error} />
      ) : designs.length === 0 ? (
        <Empty icon={PenTool} title="No designs shared yet" hint="Your designer will share renders here as soon as they're ready." />
      ) : (
        <div className="space-y-3">
          {designs.map((d) => {
            const st = STATUS[d.status] || { tone: "neutral", label: d.status };
            const docs = d.documents || [];
            const canAct = d.status === "Shared" || d.status === "Revision Requested";
            return (
              <Card key={d.id}>
                <CardBody>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-slate-900">Revision R{d.revision_number}</h3>
                        <Badge tone={st.tone}>{st.label}</Badge>
                      </div>
                      {d.title && <p className="mt-0.5 text-sm text-slate-500">{d.title}</p>}
                      <p className="mt-0.5 text-xs text-slate-400">{shortDate(d.created_at || d.updated_at)}</p>
                    </div>
                  </div>

                  {d.client_feedback && d.status === "Revision Requested" && (
                    <div className="mt-3 rounded-xl bg-sky-50 p-3 text-sm text-sky-900">
                      <span className="font-medium">Your note: </span>{d.client_feedback}
                    </div>
                  )}

                  {docs.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {docs.map((doc) => (
                        <button
                          key={doc.id}
                          onClick={() => download(doc)}
                          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                        >
                          <Download className="h-4 w-4 text-brand-700" />
                          <span className="max-w-[12rem] truncate">{doc.filename || doc.type}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {d.status === "Approved" ? (
                    <div className="mt-4 flex items-center gap-1.5 border-t border-slate-100 pt-4 text-sm font-medium text-emerald-600">
                      <CheckCircle2 className="h-4 w-4" /> You approved this design
                    </div>
                  ) : (
                    <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
                      <Button variant="secondary" onClick={() => setDialog(d)} disabled={!canAct}>
                        <MessageSquarePlus className="h-4 w-4" /> Request changes
                      </Button>
                      <Button onClick={() => approve(d)} loading={approving === d.id} disabled={!canAct}>
                        <CheckCircle2 className="h-4 w-4" /> Approve
                      </Button>
                    </div>
                  )}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}

      {dialog && <RequestChangesDialog design={dialog} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />}
    </div>
  );
}

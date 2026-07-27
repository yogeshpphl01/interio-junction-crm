/*
  Estimates — the customer's SHARED / ACCEPTED quotes with line items. A shared
  estimate can be accepted here (POST /client/estimates/{id}/accept), which is the
  same transition that unlocks the booking payment. Drafts never reach this app.
*/
import { useState } from "react";
import { FileText, CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { postWithStepUp, apiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardBody, Empty, PageLoader } from "@/components/ui";
import { money, shortDate } from "@/lib/format";

const STATUS_TONE = { shared: "amber", accepted: "green" };

export default function Estimates() {
  const { data, loading, error, reload } = useApi("/client/estimates");
  const { push } = useToast();
  const [openId, setOpenId] = useState(null);
  const [accepting, setAccepting] = useState(null);

  const estimates = data?.estimates || [];

  async function accept(est) {
    setAccepting(est.id);
    try {
      await postWithStepUp(`/client/estimates/${est.id}/accept`);
      push({ title: "Estimate accepted", description: `Version ${est.version} is confirmed. Our team will reach out about the booking payment.`, tone: "success" });
      await reload();
    } catch (e) {
      push({ title: "Couldn't accept estimate", description: apiError(e), tone: "error" });
    } finally {
      setAccepting(null);
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Estimates</h1>
        <p className="mt-1 text-slate-500">Review your quotes and accept when you're ready.</p>
      </div>

      {error ? (
        <Empty icon={FileText} title="Couldn't load estimates" hint={error} />
      ) : estimates.length === 0 ? (
        <Empty icon={FileText} title="No estimates yet" hint="When our team shares a quote with you, it'll appear here." />
      ) : (
        <div className="space-y-3">
          {estimates.map((est) => {
            const open = openId === est.id;
            const items = est.items || [];
            const total = est.total ?? items.reduce((s, it) => s + (Number(it.amount) || 0), 0);
            return (
              <Card key={est.id}>
                <CardBody>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-slate-900">Estimate v{est.version}</h3>
                        <Badge tone={STATUS_TONE[est.status] || "neutral"}>
                          {est.status === "accepted" ? "Accepted" : "Awaiting your approval"}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-sm text-slate-400">Shared {shortDate(est.created_at)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-400">Total</p>
                      <p className="text-lg font-semibold text-slate-900">{money(total, est.currency)}</p>
                    </div>
                  </div>

                  {items.length > 0 && (
                    <button
                      onClick={() => setOpenId(open ? null : est.id)}
                      className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800"
                    >
                      {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      {open ? "Hide" : "View"} {items.length} line item{items.length > 1 ? "s" : ""}
                    </button>
                  )}

                  {open && (
                    <div className="mt-3 overflow-hidden rounded-xl border border-slate-100">
                      <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                          <tr>
                            <th className="px-3 py-2 font-medium">Item</th>
                            <th className="px-3 py-2 text-right font-medium">Qty</th>
                            <th className="px-3 py-2 text-right font-medium">Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {items.map((it, i) => (
                            <tr key={it.id || i}>
                              <td className="px-3 py-2 text-slate-700">{it.description || it.name || it.item || "Item"}</td>
                              <td className="px-3 py-2 text-right text-slate-500">{it.quantity ?? it.qty ?? "—"}</td>
                              <td className="px-3 py-2 text-right font-medium text-slate-800">{money(it.amount, est.currency)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div className="mt-4 flex items-center justify-end border-t border-slate-100 pt-4">
                    {est.status === "accepted" ? (
                      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600">
                        <CheckCircle2 className="h-4 w-4" /> Accepted
                      </span>
                    ) : (
                      <Button onClick={() => accept(est)} loading={accepting === est.id}>
                        <CheckCircle2 className="h-4 w-4" /> Accept estimate
                      </Button>
                    )}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

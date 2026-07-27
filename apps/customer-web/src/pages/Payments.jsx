/*
  Payments — the customer's booking + milestone payments with a paid/balance
  summary. Read-only: money is collected offline / via the gateway; this is the
  customer's ledger view. Source: GET /client/payments.
*/
import { Wallet } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { Badge, Card, CardBody, Empty, PageLoader } from "@/components/ui";
import { money, shortDate } from "@/lib/format";

const PAID = new Set(["verified", "paid", "Paid"]);

function statusTone(status) {
  if (PAID.has(status)) return "green";
  if (status === "overdue") return "rose";
  return "amber";
}

function statusLabel(status) {
  if (PAID.has(status)) return "Paid";
  if (!status) return "Due";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function Payments() {
  const { data, loading, error } = useApi("/client/payments");
  if (loading) return <PageLoader />;

  const summary = data?.summary;
  const payments = data?.payments || [];
  const pct = summary && summary.contract_value > 0
    ? Math.min(100, Math.round((summary.paid / summary.contract_value) * 100))
    : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Payments</h1>
        <p className="mt-1 text-slate-500">Your booking and milestone payments.</p>
      </div>

      {error ? (
        <Empty icon={Wallet} title="Couldn't load payments" hint={error} />
      ) : (
        <>
          {summary && (
            <Card>
              <CardBody>
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <p className="text-xs font-medium text-slate-400">Paid so far</p>
                    <p className="mt-1 text-2xl font-bold text-slate-900">{money(summary.paid, summary.currency)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-medium text-slate-400">Balance</p>
                    <p className="mt-1 text-lg font-semibold text-slate-700">{money(summary.balance, summary.currency)}</p>
                  </div>
                </div>
                <div className="mt-4">
                  <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="mt-1.5 flex justify-between text-xs text-slate-400">
                    <span>{pct}% paid</span>
                    <span>of {money(summary.contract_value, summary.currency)}</span>
                  </div>
                </div>
              </CardBody>
            </Card>
          )}

          {payments.length === 0 ? (
            <Empty icon={Wallet} title="No payments yet" hint="Payment milestones will appear here as your project progresses." />
          ) : (
            <Card>
              <ul className="divide-y divide-slate-100">
                {payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 px-5 py-4">
                    <div>
                      <p className="font-medium text-slate-800">{p.milestone || (p.type === "booking" ? "Booking payment" : "Milestone payment")}</p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        {PAID.has(p.status) && p.paid_date ? `Paid ${shortDate(p.paid_date)}` : p.due_date ? `Due ${shortDate(p.due_date)}` : ""}
                        {p.method ? ` · ${p.method}` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-semibold text-slate-900">{money(p.amount, p.currency)}</span>
                      <Badge tone={statusTone(p.status)}>{statusLabel(p.status)}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

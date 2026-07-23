/*
  Home — the customer's project overview. Pulls /client/projects (lead + pipeline
  stage + project status) and /client/payments (for a balance tile). This is the
  landing screen after login.
*/
import { Link } from "react-router-dom";
import { FileText, PenTool, Wallet, FolderOpen, Factory, CheckCircle2, ArrowRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useApi } from "@/hooks/useApi";
import { Badge, Card, CardBody, Empty, PageLoader } from "@/components/ui";
import { money } from "@/lib/format";

function StageBadge({ stage_name, stage_color }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ backgroundColor: (stage_color || "#0f766e") + "1a", color: stage_color || "#0f766e" }}
    >
      {stage_name || "In progress"}
    </span>
  );
}

const QUICK = [
  { to: "/estimates", label: "Estimates", icon: FileText },
  { to: "/designs", label: "Designs", icon: PenTool },
  { to: "/payments", label: "Payments", icon: Wallet },
  { to: "/documents", label: "Documents", icon: FolderOpen },
];

export default function Home() {
  const { customer } = useAuth();
  const { data, loading, error } = useApi("/client/projects");
  const { data: pay } = useApi("/client/payments");

  const projects = data?.projects || [];
  const summary = pay?.summary;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Hello, {customer?.full_name?.split(" ")[0] || "there"} 👋
        </h1>
        <p className="mt-1 text-slate-500">Here's where your interior project stands.</p>
      </div>

      {summary && (
        <div className="grid grid-cols-3 gap-3">
          <Card><CardBody className="p-4">
            <p className="text-xs font-medium text-slate-400">Contract value</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{money(summary.contract_value, summary.currency)}</p>
          </CardBody></Card>
          <Card><CardBody className="p-4">
            <p className="text-xs font-medium text-slate-400">Paid</p>
            <p className="mt-1 text-lg font-semibold text-emerald-600">{money(summary.paid, summary.currency)}</p>
          </CardBody></Card>
          <Card><CardBody className="p-4">
            <p className="text-xs font-medium text-slate-400">Balance</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{money(summary.balance, summary.currency)}</p>
          </CardBody></Card>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {QUICK.map(({ to, label, icon: Icon }) => (
          <Link key={to} to={to} className="group">
            <Card className="transition-shadow hover:shadow-md">
              <CardBody className="flex items-center gap-3 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                  <Icon className="h-5 w-5" />
                </div>
                <span className="text-sm font-medium text-slate-700 group-hover:text-slate-900">{label}</span>
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Your project</h2>
        {loading ? (
          <PageLoader />
        ) : error ? (
          <Empty title="Couldn't load your project" hint={error} />
        ) : projects.length === 0 ? (
          <Empty title="No project yet" hint="Once our team sets up your project, it'll show up here." />
        ) : (
          <div className="space-y-3">
            {projects.map((p) => (
              <Card key={p.lead_id}>
                <CardBody>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-slate-900">{p.bhk_type || "Interior project"}</h3>
                        <StageBadge {...p} />
                      </div>
                      {p.requirements && <p className="mt-1 text-sm text-slate-500">{p.requirements}</p>}
                    </div>
                    {p.project?.project_code && (
                      <Badge tone="neutral">{p.project.project_code}</Badge>
                    )}
                  </div>

                  {p.project && (
                    <div className="mt-4 flex flex-wrap gap-4 border-t border-slate-100 pt-4 text-sm">
                      {typeof p.project.contract_value === "number" && (
                        <div>
                          <p className="text-xs text-slate-400">Contract value</p>
                          <p className="font-medium text-slate-800">{money(p.project.contract_value)}</p>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5">
                        {p.project.booking_paid ? (
                          <><CheckCircle2 className="h-4 w-4 text-emerald-600" /><span className="text-slate-600">Booking confirmed</span></>
                        ) : (
                          <span className="text-slate-400">Booking pending</span>
                        )}
                      </div>
                      {p.project.in_production && (
                        <div className="flex items-center gap-1.5">
                          <Factory className="h-4 w-4 text-brand-700" /><span className="text-slate-600">In production</span>
                        </div>
                      )}
                    </div>
                  )}

                  <Link to="/estimates" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800">
                    View estimates & designs <ArrowRight className="h-4 w-4" />
                  </Link>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

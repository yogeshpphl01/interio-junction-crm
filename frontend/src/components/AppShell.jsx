import { useState } from "react";
import { useNavigate, Link, useLocation, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { ROLE_LABEL, ROLE_COLOR } from "@/lib/constants";
import { initials } from "@/lib/format";
import {
  LayoutDashboard, Columns3, Users, Ruler, BarChart3, Settings, LogOut,
  Sparkles, Workflow, Menu, X,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, roles: ["admin", "sales", "designer", "supervisor"] },
  { to: "/pipeline", label: "Pipeline", icon: Columns3, roles: ["admin", "sales", "designer", "supervisor"] },
  { to: "/leads", label: "Leads", icon: Users, roles: ["admin", "sales"] },
  { to: "/site-visits", label: "Site Visits", icon: Ruler, roles: ["admin", "sales", "supervisor"] },
  { to: "/scoring", label: "Lead Scoring", icon: Sparkles, roles: ["admin", "sales"] },
  { to: "/automations", label: "Automations", icon: Workflow, roles: ["admin", "sales"] },
  { to: "/analytics", label: "Analytics", icon: BarChart3, roles: ["admin"] },
  { to: "/settings", label: "Settings", icon: Settings, roles: ["admin"] },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user) return null;
  const visible = NAV.filter((n) => n.roles.includes(user.role));

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen paper-bg flex">
      {/* Sidebar */}
      <aside
        data-testid="app-sidebar"
        className={`fixed lg:static z-40 lg:z-0 inset-y-0 left-0 w-72 bg-bone-paper border-r border-edge flex flex-col transition-transform lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="px-6 py-6 border-b border-edge flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3" data-testid="brand-home-link">
            <div className="w-9 h-9 rounded-md bg-clay flex items-center justify-center">
              <span className="font-serif text-white text-xl leading-none">i</span>
            </div>
            <div>
              <div className="font-serif text-lg leading-none text-ink">Interio</div>
              <div className="text-[10px] tracking-[0.18em] uppercase text-ink-muted mt-1">Junction</div>
            </div>
          </Link>
          <button
            data-testid="sidebar-close-btn"
            className="lg:hidden p-1 text-ink-soft"
            onClick={() => setMobileOpen(false)}
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto scrollbar-thin">
          {visible.map((n) => {
            const active = location.pathname === n.to || (n.to !== "/" && location.pathname.startsWith(n.to));
            const Icon = n.icon;
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={`nav-${n.to.replace("/", "") || "home"}`}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  active
                    ? "bg-bone-subtle text-ink"
                    : "text-ink-soft hover:bg-bone hover:text-ink"
                }`}
              >
                <Icon className="w-4 h-4" strokeWidth={1.75} />
                <span>{n.label}</span>
                {active && <span className="ml-auto w-1 h-4 bg-clay rounded-full" />}
              </Link>
            );
          })}
        </nav>
        <div className="px-3 py-4 border-t border-edge">
          <div className="px-3 py-2 flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-md flex items-center justify-center text-white text-xs font-semibold"
              style={{ background: ROLE_COLOR[user.role] || "#8A5A3B" }}
              data-testid="user-avatar"
            >
              {initials(user.full_name || user.email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-ink truncate">{user.full_name}</div>
              <div className="text-[11px] text-ink-muted truncate">{ROLE_LABEL[user.role]}</div>
            </div>
            <button
              onClick={onLogout}
              data-testid="logout-btn"
              className="p-2 rounded hover:bg-bone-subtle text-ink-soft"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 bg-ink/30 z-30 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      <main className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 backdrop-blur bg-bone/80 border-b border-edge">
          <div className="px-6 lg:px-10 py-4 flex items-center gap-4">
            <button
              data-testid="sidebar-open-btn"
              className="lg:hidden p-2 -ml-2 text-ink-soft"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex-1">
              <div className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">Interio Junction CRM</div>
              <div className="font-serif text-xl text-ink leading-tight">{getTitle(location.pathname)}</div>
            </div>
            <div
              className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-bone-subtle border border-edge"
              data-testid="role-badge"
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: ROLE_COLOR[user.role] }} />
              <span className="text-xs font-medium text-ink">{ROLE_LABEL[user.role]}</span>
            </div>
          </div>
        </header>
        <div className="flex-1">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function getTitle(path) {
  if (path === "/") return "Command Center";
  if (path.startsWith("/pipeline")) return "Pipeline";
  if (path.startsWith("/leads/")) return "Lead Details";
  if (path.startsWith("/leads")) return "Leads";
  if (path.startsWith("/site-visits")) return "Site Visits";
  if (path.startsWith("/scoring")) return "Lead Scoring";
  if (path.startsWith("/automations")) return "Automations";
  if (path.startsWith("/analytics")) return "Analytics";
  if (path.startsWith("/settings")) return "Settings";
  return "Interio Junction";
}

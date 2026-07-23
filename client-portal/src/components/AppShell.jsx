/*
  Authenticated layout for the customer portal: a left sidebar on desktop and a
  bottom tab bar on mobile (customers mostly visit on phones). The header shows
  who's signed in and a sign-out control. Content renders via <Outlet/>.
*/
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Home, FileText, PenTool, Wallet, FolderOpen, MessageCircle, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/estimates", label: "Estimates", icon: FileText },
  { to: "/designs", label: "Designs", icon: PenTool },
  { to: "/payments", label: "Payments", icon: Wallet },
  { to: "/documents", label: "Documents", icon: FolderOpen },
  { to: "/chat", label: "Messages", icon: MessageCircle },
];

function initials(name) {
  return (name || "C")
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function AppShell() {
  const { customer, logout } = useAuth();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="flex h-16 items-center gap-3 px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-700 text-sm font-bold text-white">IJ</div>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-slate-900">Interio Junction</p>
            <p className="text-xs text-slate-400">Customer Portal</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive ? "bg-brand-50 text-brand-800" : "text-slate-600 hover:bg-slate-100"
                )
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-100 p-3">
          <div className="flex items-center gap-3 rounded-xl px-3 py-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-800">
              {initials(customer?.full_name)}
            </div>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-sm font-medium text-slate-800">{customer?.full_name}</p>
              <p className="truncate text-xs text-slate-400">{customer?.phone}</p>
            </div>
            <button onClick={onLogout} title="Sign out" className="text-slate-400 hover:text-rose-600">
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-700 text-xs font-bold text-white">IJ</div>
          <span className="text-sm font-semibold text-slate-900">Interio Junction</span>
        </div>
        <button onClick={onLogout} className="text-slate-400 hover:text-rose-600">
          <LogOut className="h-5 w-5" />
        </button>
      </header>

      {/* Content */}
      <main className="lg:pl-64">
        <div className="mx-auto w-full max-w-5xl px-4 pb-24 pt-6 lg:px-8 lg:pb-10">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex items-stretch justify-around border-t border-slate-200 bg-white/95 backdrop-blur lg:hidden">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
                isActive ? "text-brand-700" : "text-slate-400"
              )
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

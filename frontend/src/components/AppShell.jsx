/*
  <component name="AppShell" layer="frontend-layout">
    <purpose>Authenticated chrome: left sidebar nav, top header with page title +
    role badge, and an <Outlet/> for the active page. Collapsible on mobile.</purpose>
    <nav-visibility>Each NAV item is shown when the user's built-in role is listed
    (`roles`) OR the user holds the item's permission (`perm`, any-of) — so custom
    account categories (Module 7) see exactly the sections their toggles grant.
    `always` items (Command Center, Pipeline) are visible to every signed-in user.</nav-visibility>
  </component>
*/
import { useState } from "react";
import { useNavigate, Link, useLocation, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { ROLE_LABEL, ROLE_COLOR } from "@/lib/constants";
import { initials } from "@/lib/format";
import ChangePasswordModal from "@/components/ChangePasswordModal";
import EditProfileModal from "@/components/EditProfileModal";
import {
  LayoutDashboard, Columns3, Users, Ruler, BarChart3, Settings, LogOut,
  Sparkles, Workflow, Menu, X, ScrollText, Bell, KeyRound, Pencil,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Command Center", icon: LayoutDashboard, always: true },
  { to: "/pipeline", label: "Pipeline", icon: Columns3, always: true },
  { to: "/leads", label: "Leads", icon: Users, roles: ["ceo", "admin", "manager", "sales"], perm: "leads.view_all" },
  { to: "/site-visits", label: "Site Visits", icon: Ruler, roles: ["ceo", "admin", "manager", "sales", "supervisor"], perm: "measurements.manage" },
  { to: "/scoring", label: "Lead Scoring", icon: Sparkles, roles: ["ceo", "admin", "manager", "sales"], perm: "scoring.manage" },
  { to: "/automations", label: "Automations", icon: Workflow, roles: ["ceo", "admin", "manager", "sales"], perm: "automations.manage" },
  { to: "/notifications", label: "Notifications", icon: Bell, roles: ["ceo", "admin"], perm: "notifications.manage" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, roles: ["ceo", "admin"], perm: "analytics.company" },
  { to: "/audit", label: "Audit Log", icon: ScrollText, roles: ["ceo", "admin"], perm: "audit.view" },
  { to: "/settings", label: "Settings", icon: Settings, roles: ["ceo", "admin"], perm: ["users.manage", "roles.manage"] },
];

// Visible when an `always` item, the user's built-in role is listed, or the user
// holds one of the item's permissions (the Module 7 custom-category path).
function canSee(item, user) {
  if (item.always) return true;
  if (item.roles && item.roles.includes(user.role)) return true;
  const held = user.permissions || [];
  const wanted = item.perm ? (Array.isArray(item.perm) ? item.perm : [item.perm]) : [];
  return wanted.some((p) => held.includes(p));
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showChangePwd, setShowChangePwd] = useState(false);
  const [showEditProfile, setShowEditProfile] = useState(false);

  if (!user) return null;
  const visible = NAV.filter((n) => canSee(n, user));
  // Prefer server-supplied label/colour (covers custom categories), fall back to the built-in map.
  const roleLabel = user.role_label || ROLE_LABEL[user.role] || user.role;
  const roleColor = user.role_color || ROLE_COLOR[user.role] || "#8A5A3B";

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
              style={{ background: roleColor }}
              data-testid="user-avatar"
            >
              {initials(user.full_name || user.email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-ink truncate">{user.full_name}</div>
              <div className="text-[11px] text-ink-muted truncate">{roleLabel}</div>
            </div>
            <button
              onClick={() => setShowEditProfile(true)}
              data-testid="edit-profile-btn"
              className="p-2 rounded hover:bg-bone-subtle text-ink-soft"
              title="Edit profile"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowChangePwd(true)}
              data-testid="change-password-btn"
              className="p-2 rounded hover:bg-bone-subtle text-ink-soft"
              title="Change password"
            >
              <KeyRound className="w-4 h-4" />
            </button>
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
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: roleColor }} />
              <span className="text-xs font-medium text-ink">{roleLabel}</span>
            </div>
          </div>
        </header>
        <div className="flex-1">
          <Outlet />
        </div>
      </main>

      {showChangePwd && <ChangePasswordModal onClose={() => setShowChangePwd(false)} />}
      {showEditProfile && <EditProfileModal onClose={() => setShowEditProfile(false)} />}
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
  if (path.startsWith("/notifications")) return "Notifications";
  if (path.startsWith("/analytics")) return "Analytics";
  if (path.startsWith("/audit")) return "Audit Log";
  if (path.startsWith("/settings")) return "Settings";
  return "Interio Junction";
}

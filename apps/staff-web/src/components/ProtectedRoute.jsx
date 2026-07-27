/*
  <component name="ProtectedRoute" layer="frontend-routing">
    <purpose>Route guard. Shows a loader while the session resolves, redirects to
    /login when anonymous, and to "/" when the user is allowed by neither `roles`
    nor `perm`. A custom-category user passes if they hold the route's permission
    (`perm` may be a single key or an any-of array).</purpose>
    <note>UI gating only — the backend independently enforces RBAC per request.</note>
  </component>
*/
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function ProtectedRoute({ children, roles, perm }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading || user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bone">
        <div className="text-ink-muted text-sm tracking-wider uppercase animate-pulse">Loading…</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (roles) {
    const byRole = roles.includes(user.role);
    const wanted = perm ? (Array.isArray(perm) ? perm : [perm]) : [];
    const held = user.permissions || [];
    const byPerm = wanted.some((p) => held.includes(p));
    if (!byRole && !byPerm) return <Navigate to="/" replace />;
  }
  return children;
}

/*
  <component name="ProtectedRoute" layer="frontend-routing">
    <purpose>Route guard. Shows a loader while the session resolves, redirects to
    /login when anonymous, and to "/" when the user's role is not in `roles`.</purpose>
    <note>UI gating only — the backend independently enforces RBAC per request.</note>
  </component>
*/
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function ProtectedRoute({ children, roles }) {
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
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

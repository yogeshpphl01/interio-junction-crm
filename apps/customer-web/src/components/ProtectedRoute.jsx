/* Gate authenticated pages: bounce anonymous visitors to /login, show a loader
   while the session is still resolving. */
import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { PageLoader } from "@/components/ui";

export function ProtectedRoute({ children }) {
  const { customer, loading } = useAuth();
  if (loading || customer === null) return <PageLoader />;
  if (!customer) return <Navigate to="/login" replace />;
  return children;
}

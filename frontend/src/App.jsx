/*
  <module name="App" layer="frontend-routing">
    <purpose>Top-level router. Wraps everything in AuthProvider, exposes /login,
    and renders all authenticated pages inside the AppShell (sidebar + header)
    behind ProtectedRoute. Admin-only pages add a role guard.</purpose>
    <routes>/ (Command Center), /pipeline, /leads, /leads/:id, /site-visits,
    /scoring, /automations, /analytics, /settings, /audit, /notifications.</routes>
  </module>
*/
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import AppShell from "@/components/AppShell";
import Login from "@/pages/Login";
import CommandCenter from "@/pages/CommandCenter";
import Pipeline from "@/pages/Pipeline";
import Projects from "@/pages/Projects";
import LeadDetail from "@/pages/LeadDetail";
import Leads from "@/pages/Leads";
import SiteVisits from "@/pages/SiteVisits";
import LeadScoring from "@/pages/LeadScoring";
import Automations from "@/pages/Automations";
import Settings from "@/pages/Settings";
import Audit from "@/pages/Audit";
import NotificationSettings from "@/pages/NotificationSettings";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<CommandCenter />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/leads" element={<Leads />} />
            <Route path="/leads/:id" element={<LeadDetail />} />
            <Route path="/site-visits" element={<SiteVisits />} />
            <Route
              path="/scoring"
              element={
                <ProtectedRoute roles={["ceo", "admin", "manager", "sales"]} perm="scoring.manage">
                  <LeadScoring />
                </ProtectedRoute>
              }
            />
            <Route
              path="/automations"
              element={
                <ProtectedRoute roles={["ceo", "admin", "manager", "sales"]} perm="automations.manage">
                  <Automations />
                </ProtectedRoute>
              }
            />
            <Route
              path="/analytics"
              element={
                <ProtectedRoute roles={["ceo", "admin"]} perm="analytics.company">
                  <CommandCenter />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute roles={["ceo", "admin"]} perm={["users.manage", "roles.manage"]}>
                  <Settings />
                </ProtectedRoute>
              }
            />
            <Route
              path="/audit"
              element={
                <ProtectedRoute roles={["ceo", "admin"]} perm="audit.view">
                  <Audit />
                </ProtectedRoute>
              }
            />
            <Route
              path="/notifications"
              element={
                <ProtectedRoute roles={["ceo", "admin"]} perm="notifications.manage">
                  <NotificationSettings />
                </ProtectedRoute>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

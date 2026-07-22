/*
  <module name="App" layer="client-portal-routing">
    <purpose>Top-level router for the CUSTOMER portal. AuthProvider + ToastProvider
    wrap everything; /login is public; all other pages render inside AppShell
    behind ProtectedRoute (customer session required).</purpose>
    <routes>/login, / (Home), /estimates, /designs, /payments, /documents, /chat.</routes>
  </module>
*/
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/Toast";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import AppShell from "@/components/AppShell";
import Login from "@/pages/Login";
import Home from "@/pages/Home";
import Estimates from "@/pages/Estimates";
import Designs from "@/pages/Designs";
import Payments from "@/pages/Payments";
import Documents from "@/pages/Documents";
import Chat from "@/pages/Chat";

export default function App() {
  return (
    <ToastProvider>
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
              <Route index element={<Home />} />
              <Route path="/estimates" element={<Estimates />} />
              <Route path="/designs" element={<Designs />} />
              <Route path="/payments" element={<Payments />} />
              <Route path="/documents" element={<Documents />} />
              <Route path="/chat" element={<Chat />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}

/*
  <module name="AuthContext" layer="client-portal-state">
    <purpose>
      Customer session state + actions via useAuth(). Login is phone + OTP,
      mirroring the Client mobile app and the /client/auth BFF exactly. On mount,
      if a stored access token exists we resolve the session with GET /client/me.
    </purpose>
    <customer-states>null = checking · false = anonymous · object = logged in.</customer-states>
  </module>
*/
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, apiError, tokens } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [customer, setCustomer] = useState(null); // null=checking, false=anon, object=logged in
  const [loading, setLoading] = useState(true);

  const resolve = useCallback(async () => {
    if (!tokens.access) {
      setCustomer(false);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/client/me");
      setCustomer(data.customer || false);
    } catch {
      tokens.clear();
      setCustomer(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    resolve();
  }, [resolve]);

  // Step 1 — ask the backend to send a login code. Response is intentionally
  // generic (no "is this number registered?" oracle), so we just surface ok.
  const requestOtp = async (phone) => {
    try {
      const { data } = await api.post("/client/auth/request-otp", { phone });
      return { ok: true, message: data?.message };
    } catch (e) {
      return { ok: false, error: apiError(e) };
    }
  };

  // Step 2 — verify the code, store the customer tokens, become logged in.
  const verifyOtp = async (phone, code) => {
    try {
      const { data } = await api.post("/client/auth/verify-otp", { phone, code });
      tokens.set(data);
      setCustomer(data.customer);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: apiError(e) };
    }
  };

  const logout = async () => {
    try {
      await api.post("/client/auth/logout");
    } catch {
      /* bearer tokens are stateless; a failed logout call is harmless */
    }
    tokens.clear();
    setCustomer(false);
  };

  return (
    <AuthCtx.Provider value={{ customer, loading, requestOtp, verifyOtp, logout, refresh: resolve, setCustomer }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

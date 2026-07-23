/*
  <module name="AuthContext" layer="frontend-state">
    <purpose>App-wide auth state + actions (login / logout / refresh) exposed via
    the useAuth() hook. On mount it calls GET /auth/me to resolve the session.</purpose>
    <user-states>null = still checking · false = anonymous · object = logged in.</user-states>
    <token>On login the access token is mirrored to localStorage (ij_api token)
    as a bearer fallback for hosts that drop cookies (see lib/api.js).</token>
  </module>
*/
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { beginPasskeyLogin, isPasskeyCancel } from "@/lib/webauthn";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = anon, object = logged in
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      setUser(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      // Staff MFA (P1-6): when a second factor is enrolled the backend withholds
      // the session and returns a short-lived pre-auth token instead. The Login
      // page then collects a TOTP/backup code and calls completeMfa().
      if (data?.mfa_required) return { ok: false, mfaRequired: true, mfaToken: data.mfa_token };
      if (data?.access_token) localStorage.setItem("ij_access_token", data.access_token);
      setUser(data.user);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: formatApiErrorDetail(e?.response?.data?.detail) || e.message };
    }
  };

  // Step 2 of an MFA login: exchange the pre-auth token + code for a full session.
  const completeMfa = async (mfaToken, code) => {
    try {
      const { data } = await api.post("/auth/mfa/verify", { mfa_token: mfaToken, code });
      if (data?.access_token) localStorage.setItem("ij_access_token", data.access_token);
      setUser(data.user);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: formatApiErrorDetail(e?.response?.data?.detail) || e.message };
    }
  };

  // Phishing-resistant sign-in with a passkey (A8). No password, no MFA step —
  // the WebAuthn assertion mints a full AAL2 session directly.
  const loginWithPasskey = async (email) => {
    try {
      const data = await beginPasskeyLogin(email);
      if (data?.access_token) localStorage.setItem("ij_access_token", data.access_token);
      setUser(data.user);
      return { ok: true };
    } catch (e) {
      if (isPasskeyCancel(e)) return { ok: false, cancelled: true };
      return { ok: false, error: formatApiErrorDetail(e?.response?.data?.detail) || "Passkey sign-in failed" };
    }
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {}
    localStorage.removeItem("ij_access_token");
    setUser(false);
  };

  return (
    <AuthCtx.Provider value={{ user, loading, login, completeMfa, loginWithPasskey, logout, refresh, setUser }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

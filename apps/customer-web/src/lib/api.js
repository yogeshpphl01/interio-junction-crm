/*
  <module name="lib/api" layer="client-portal-data">
    <purpose>
      Axios client for the CUSTOMER portal. Deliberately BEARER-ONLY (no cookies /
      no withCredentials): the customer session lives entirely in localStorage
      under its own keys, so even when the portal is served from the same origin
      as the company CRM it never shares a cookie jar with the staff app. The
      backend already rejects a customer token on staff routes and vice-versa
      (dual-BFF), so the two apps are isolated on both ends.
    </purpose>
    <tokens>
      ij_customer_token          — short-lived customer access JWT (Authorization: Bearer)
      ij_customer_refresh        — customer refresh JWT (exchanged on 401)
      ij_customer_stepup / _exp  — a fresh step-up token for high-risk actions
    </tokens>
  </module>
*/
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API_BASE = `${BACKEND_URL}/api`;

export const TOKEN_KEY = "ij_customer_token";
export const REFRESH_KEY = "ij_customer_refresh";
const STEPUP_KEY = "ij_customer_stepup";
const STEPUP_EXP_KEY = "ij_customer_stepup_exp";

export const tokens = {
  get access() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(TOKEN_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(STEPUP_KEY);
    localStorage.removeItem(STEPUP_EXP_KEY);
  },
};

export const api = axios.create({ baseURL: API_BASE });

// Absolute URL for a backend-relative path (e.g. a signed "/api/documents/download?token=…").
// Same-origin by default (BACKEND_URL=""), so the value is returned unchanged.
export const assetUrl = (pathFromApi) => `${BACKEND_URL}${pathFromApi}`;

// --- request: attach the customer bearer token (+ a fresh step-up token if any) ---
api.interceptors.request.use((config) => {
  const token = tokens.access;
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  const su = localStorage.getItem(STEPUP_KEY);
  const exp = Number(localStorage.getItem(STEPUP_EXP_KEY) || 0);
  if (su && exp > Date.now()) {
    config.headers["X-Client-Step-Up"] = su;
  }
  return config;
});

// --- response: transparently refresh the access token once on a 401 ---
let refreshing = null;
const AUTH_PATHS = ["/client/auth/verify-otp", "/client/auth/request-otp", "/client/auth/refresh"];

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config || {};
    const status = error?.response?.status;
    const isAuthCall = AUTH_PATHS.some((p) => (original.url || "").includes(p));
    if (status === 401 && !original._retried && !isAuthCall && tokens.refresh) {
      original._retried = true;
      try {
        refreshing =
          refreshing ||
          axios.post(`${API_BASE}/client/auth/refresh`, { refresh_token: tokens.refresh });
        const { data } = await refreshing;
        refreshing = null;
        if (data?.access_token) {
          localStorage.setItem(TOKEN_KEY, data.access_token);
          original.headers = original.headers || {};
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        }
      } catch {
        refreshing = null;
      }
      // Refresh failed → session is dead. Drop tokens and bounce to login.
      tokens.clear();
      if (!location.pathname.endsWith("/login")) location.assign("/login");
    }
    return Promise.reject(error);
  }
);

/**
 * Mint a fresh customer step-up token (from an on-device confirmation) and stash
 * it so the next high-risk request carries X-Client-Step-Up. No-op-safe: if the
 * backend has step-up disabled this simply never gets exercised.
 */
export async function requestStepUp() {
  const { data } = await api.post("/client/auth/step-up");
  if (data?.step_up_token) {
    localStorage.setItem(STEPUP_KEY, data.step_up_token);
    localStorage.setItem(
      STEPUP_EXP_KEY,
      String(Date.now() + (data.expires_in || 300) * 1000 - 5000)
    );
  }
  return data;
}

/**
 * POST a high-risk action, transparently satisfying a step-up challenge. If the
 * backend answers 403 asking for confirmation (CLIENT_STEP_UP_ENABLED), we mint a
 * step-up token and retry exactly once. When step-up is disabled this is a plain
 * POST. `confirm` (optional) lets the caller gate the token mint behind a UI
 * prompt / biometric — return false to abort.
 */
export async function postWithStepUp(url, body, { confirm } = {}) {
  try {
    return await api.post(url, body);
  } catch (e) {
    const status = e?.response?.status;
    const detail = e?.response?.data?.detail || "";
    const needsStepUp = status === 403 && /confirm|step-up|biometr/i.test(String(detail));
    if (!needsStepUp) throw e;
    if (confirm && !(await confirm())) throw e;
    await requestStepUp();
    return await api.post(url, body); // retry once, now carrying X-Client-Step-Up
  }
}

// Turn a FastAPI error detail (string | array | object) into one readable line.
export function apiError(e) {
  const detail = e?.response?.data?.detail;
  if (detail == null) return e?.message || "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((x) => (x && typeof x.msg === "string" ? x.msg : JSON.stringify(x))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

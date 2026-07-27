/*
  <module name="lib/api" layer="frontend-data">
    <purpose>Shared axios client. Base URL = REACT_APP_BACKEND_URL + "/api",
    sends cookies (withCredentials) and also attaches a bearer token from
    localStorage as a fallback for hosts that drop cookies.</purpose>
    <helper>formatApiErrorDetail(): turn FastAPI error detail (string | array |
    object) into a single human-readable message for toasts.</helper>
  </module>
*/
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// Add bearer token fallback (some preview hosts don't propagate cookies).
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ij_access_token");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---- Step-up (re-authentication) bridge ----------------------------------
// Sensitive actions (payment confirm/refund, approvals, role change, delete)
// can answer 403 asking for a fresh second factor (P1-9). A UI provider
// registers a handler here that prompts for a code and returns a short-lived
// elevation token; the interceptor then replays the request with the
// X-Step-Up-Token header. Centralised, so no individual call site changes.
let stepUpHandler = null;
export function setStepUpHandler(fn) {
  stepUpHandler = fn;
}

function needsStepUp(error) {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  return status === 403 && typeof detail === "string" && /step[-\s]?up/i.test(detail);
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config || {};
    if (needsStepUp(error) && !original._steppedUp && stepUpHandler) {
      original._steppedUp = true;
      const elevation = await stepUpHandler(); // resolves to a token, or null if cancelled
      if (elevation) {
        original.headers = original.headers || {};
        original.headers["X-Step-Up-Token"] = elevation;
        return api(original); // replay the original request, now elevated
      }
    }
    return Promise.reject(error);
  }
);

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

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

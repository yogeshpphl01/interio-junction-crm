// Serves the built staff CRM (../../build) AND mocks the staff /api/* BFF on one
// origin. Used by staff-crm.e2e.mjs. Stateful for the erasure queue so the
// erase/reject flows behave like the real backend.
import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BUILD_DIR = join(__dirname, "..", "..", "build");

const PASSWORD = "interio2026";
const MFA_PASSWORD = "mfapass"; // this account is enrolled in two-factor
const USER = {
  id: "u-1", email: "admin@interiojunction.com", full_name: "Admin User",
  role: "ceo", role_label: "CEO", role_color: "#5C3A21", recovery_email: "admin@example.com",
  aal: 2,
  permissions: [
    "users.manage", "roles.manage", "automations.manage", "notifications.manage",
    "audit.view", "analytics.company", "scoring.manage", "chat.access",
    "leads.view_all", "measurements.manage",
  ],
};

const COMMAND_CENTER = {
  scope: "company",
  kpis: { total_pipeline: 4250000, forecast: 1800000, win_rate: 34, won_count: 12, cycle_days: 41 },
  forecast_trend: [{ name: "Jul", value: 120000 }, { name: "Aug", value: 210000 }, { name: "Sep", value: 320000 }],
  funnel: [
    { stage: 1, name: "Enquiry", count: 40, color: "#8A5A3B" },
    { stage: 4, name: "Design", count: 18, color: "#0F766E" },
    { stage: 6, name: "Delivered", count: 12, color: "#4A5D23" },
  ],
  by_source: [{ name: "Meta", count: 22 }, { name: "Referral", count: 14 }],
  by_lifecycle: [{ phase: "design", count: 9 }, { phase: "production", count: 6 }],
  dropoff_by_stage: [{ stage: 2, short: "S2", count: 5 }, { stage: 3, short: "S3", count: 3 }],
};

function freshState() {
  return {
    erasure: [{
      id: "er-1", customer_id: "cust-9", customer_name: "Ravi Kumar", status: "pending",
      reason: "No longer interested", requested_at: "2026-07-20T10:00:00Z", already_erased: false,
    }],
    retention: { notified: 2, erased: 1, review_due: 0, dry_run: true },
  };
}

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2",
  ".woff": "font/woff", ".map": "application/json",
};

function json(res, code, obj) {
  res.writeHead(code, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type,X-Step-Up-Token",
    "Access-Control-Allow-Credentials": "true",
  });
  res.end(JSON.stringify(obj));
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString()); } catch { return {}; }
}

async function handleApi(req, res, path, url, state) {
  if (req.method === "OPTIONS") return json(res, 204, {});
  const authed = !!req.headers["authorization"];

  if (req.method === "POST") {
    const body = await readBody(req);
    if (path === "/api/auth/login") {
      if (body.password === MFA_PASSWORD) return json(res, 200, { mfa_required: true, mfa_token: "pending-tok" });
      if (body.password !== PASSWORD) return json(res, 401, { detail: "Invalid email or password" });
      return json(res, 200, { user: USER, access_token: "staff-access", refresh_token: "staff-refresh" });
    }
    if (path === "/api/auth/mfa/verify") {
      return json(res, 200, { user: USER, access_token: "staff-access", refresh_token: "staff-refresh" });
    }
    if (path === "/api/auth/logout") return json(res, 200, { ok: true });

    const erase = path.match(/^\/api\/customers\/([^/]+)\/erase$/);
    if (erase) {
      for (const r of state.erasure) {
        if (r.customer_id === erase[1]) { r.status = "completed"; r.already_erased = true; }
      }
      return json(res, 200, { ok: true, erased: true, customer_id: erase[1] });
    }
    const reject = path.match(/^\/api\/erasure-requests\/([^/]+)\/reject$/);
    if (reject) {
      for (const r of state.erasure) if (r.id === reject[1]) r.status = "rejected";
      return json(res, 200, { ok: true, status: "rejected" });
    }
    if (path === "/api/retention/run") {
      return json(res, 200, { ok: true, notified: 2, erased: 1, review_due: 0 });
    }
    return json(res, 200, { ok: true });
  }

  // GET
  if (path === "/api/auth/me") return authed ? json(res, 200, USER) : json(res, 401, { detail: "unauthorized" });
  if (path === "/api/analytics/command-center") return json(res, 200, COMMAND_CENTER);
  if (path === "/api/auth/mfa/status") return json(res, 200, { enrolled: true, aal: 2, backup_codes_remaining: 5 });
  if (path === "/api/auth/passkey/list") return json(res, 200, { passkeys: [] });
  if (path === "/api/retention/preview") return json(res, 200, state.retention);
  if (path === "/api/erasure-requests") {
    const status = url.searchParams.get("status") || "pending";
    const rows = status === "all" ? state.erasure : state.erasure.filter((r) => r.status === status);
    return json(res, 200, rows);
  }
  return json(res, 200, []); // quiet default for every other list screen
}

async function serveStatic(res, path) {
  let rel = normalize(path).replace(/^(\.\.[/\\])+/, "");
  if (rel === "/" || rel === "\\" || rel === "") rel = "/index.html";
  const file = join(BUILD_DIR, rel);
  try {
    const s = await stat(file);
    const target = s.isDirectory() ? join(file, "index.html") : file;
    const data = await readFile(target);
    res.writeHead(200, { "Content-Type": MIME[extname(target)] || "application/octet-stream" });
    res.end(data);
  } catch {
    try {
      const data = await readFile(join(BUILD_DIR, "index.html")); // SPA fallback
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(data);
    } catch {
      res.writeHead(404); res.end("build/ not found — run `npm run build` first");
    }
  }
}

export function createServer() {
  const state = freshState();
  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://localhost");
      if (url.pathname.startsWith("/api/")) return await handleApi(req, res, url.pathname, url, state);
      return await serveStatic(res, url.pathname);
    } catch (e) {
      res.writeHead(500); res.end(String(e));
    }
  });
}

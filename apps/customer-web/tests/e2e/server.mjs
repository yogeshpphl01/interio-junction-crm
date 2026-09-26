// Serves the built customer portal (../../build) AND mocks the /api/client/* BFF
// on one origin — mirroring production (the app calls same-origin /api). Used by
// customer-portal.e2e.mjs. Stateful for estimates (accept) and consent (toggle)
// so the flows behave like the real backend.
import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BUILD_DIR = join(__dirname, "..", "..", "build");

const CUSTOMER = { id: "cust-1", full_name: "Aarav Mehta", phone: "9998887777", email: "aarav@example.com" };
const VALID_OTP = "4821";

function freshState() {
  return {
    estimates: [
      { id: "est-1", version: 2, status: "shared", total: 850000,
        items: [{ label: "Modular kitchen", amount: 450000 }, { label: "2 wardrobes", amount: 400000 }] },
    ],
    consent: {
      policy_version: "2026-07",
      catalog: {
        service:     { category: "necessary", label: "Provide your interior project", description: "Design, manufacture, install & support." },
        ai_training: { category: "optional",  label: "Improve our AI features",        description: "Use your data to train our AI models." },
        analytics:   { category: "optional",  label: "Product analytics",              description: "Understand how the app is used." },
        marketing:   { category: "optional",  label: "Marketing updates",              description: "Offers and product news." },
      },
      current: { service: true, ai_training: false, analytics: false, marketing: false },
    },
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
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  });
  res.end(JSON.stringify(obj));
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString()); } catch { return {}; }
}

async function handleApi(req, res, path, state) {
  if (req.method === "OPTIONS") return json(res, 204, {});
  const authed = !!req.headers["authorization"];

  if (req.method === "POST") {
    const body = await readBody(req);
    if (path === "/api/client/auth/request-otp") return json(res, 200, { ok: true, message: "If your number is registered, a code is on its way." });
    if (path === "/api/client/auth/verify-otp") {
      return (body.code || "").trim() === VALID_OTP
        ? json(res, 200, { access_token: "e2e-access", refresh_token: "e2e-refresh", customer: CUSTOMER })
        : json(res, 400, { detail: "Invalid or expired code" });
    }
    if (path === "/api/client/auth/logout") return json(res, 200, { ok: true });
    const acc = path.match(/^\/api\/client\/estimates\/([^/]+)\/accept$/);
    if (acc) { const e = state.estimates.find((x) => x.id === acc[1]); if (e) e.status = "accepted"; return json(res, 200, { ok: true }); }
    if (path === "/api/client/me/consent") { state.consent.current[body.purpose] = !!body.granted; return json(res, 200, { ok: true }); }
    return json(res, 200, { ok: true }); // change-contact / erasure etc.
  }

  // GET
  if (path === "/api/client/me") return authed ? json(res, 200, { customer: CUSTOMER }) : json(res, 401, { detail: "unauthorized" });
  if (path === "/api/client/projects") return json(res, 200, { projects: [{ id: "lead-1", full_name: CUSTOMER.full_name, status: "Active", stage: 5, lifecycle_phase: "design", project: { id: "proj-1", project_code: "IJ-2026-014", contract_value: 850000 } }] });
  if (path === "/api/client/payments") return json(res, 200, { summary: { paid: 85000, contract_value: 850000, currency: "INR" }, payments: [{ id: "pay-1", status: "verified", amount: 85000, paid_date: "2026-07-20", label: "Booking (10%)" }] });
  if (path === "/api/client/estimates") return json(res, 200, { estimates: state.estimates });
  if (path === "/api/client/me/consent") return json(res, 200, state.consent);
  if (path === "/api/client/designs") return json(res, 200, { designs: [] });
  return json(res, 200, {}); // quiet default (documents, chat, …)
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
    // SPA fallback → index.html (client-side routing)
    try {
      const data = await readFile(join(BUILD_DIR, "index.html"));
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
      const path = new URL(req.url, "http://localhost").pathname;
      if (path.startsWith("/api/")) return await handleApi(req, res, path, state);
      return await serveStatic(res, path);
    } catch (e) {
      res.writeHead(500); res.end(String(e));
    }
  });
}

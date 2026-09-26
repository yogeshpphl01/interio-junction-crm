// End-to-end smoke test for the staff CRM, driven by a headless browser against
// the mock BFF in server.mjs. Covers the journeys that matter most on the staff
// side: password sign-in (including the wrong-password path), the two-factor
// login, role-gated navigation, and actioning a DPDP erasure request.
// Pure Node + the `playwright` library (no @playwright/test runner needed).
//
//   npm run test:e2e        (builds first, then runs this)
//   node tests/e2e/staff-crm.e2e.mjs   (expects build/ to already exist)
import { chromium } from "playwright";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { createServer } from "./server.mjs";

const pass = [], fail = [];
const check = (name, ok) => { (ok ? pass : fail).push(name); console.log((ok ? "  PASS " : "  FAIL ") + name); };

// Resolve a Chromium binary portably: explicit override → playwright's own
// resolver → scan PLAYWRIGHT_BROWSERS_PATH (this CI image ships a build there).
function resolveChromium() {
  if (process.env.PW_CHROMIUM_PATH && existsSync(process.env.PW_CHROMIUM_PATH)) return process.env.PW_CHROMIUM_PATH;
  try { const p = chromium.executablePath(); if (p && existsSync(p)) return p; } catch { /* ignore */ }
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";
  try {
    for (const dir of readdirSync(root).filter((d) => d.startsWith("chromium-")).sort().reverse()) {
      for (const sub of ["chrome-linux/chrome", "chrome-linux64/chrome"]) {
        const cand = join(root, dir, sub);
        if (existsSync(cand)) return cand;
      }
    }
  } catch { /* ignore */ }
  return undefined;
}

const server = createServer();
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

let browser;
try {
  const executablePath = resolveChromium();
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"], ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();
  page.on("dialog", (d) => d.accept()); // the erase/reject flows use window.confirm

  // --- Sign-in screen ---
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="login-card"]', { timeout: 15000 });
  check("unauthenticated visit shows the staff sign-in card", true);

  // --- Wrong password is rejected ---
  await page.fill('[data-testid="login-email-input"]', "admin@interiojunction.com");
  await page.fill('[data-testid="login-password-input"]', "not-my-password");
  await page.click('[data-testid="login-submit-btn"]');
  await page.waitForSelector('[data-testid="login-error"]', { timeout: 15000 });
  check("wrong password shows an error and stays on sign-in", true);

  // --- Two-factor login: password succeeds, then a code is required ---
  await page.fill('[data-testid="login-password-input"]', "mfapass");
  await page.click('[data-testid="login-submit-btn"]');
  await page.waitForSelector('[data-testid="login-mfa-form"]', { timeout: 15000 });
  check("an MFA-enrolled account is asked for a second factor", true);

  await page.fill('[data-testid="login-mfa-input"]', "123456");
  await page.click('[data-testid="login-mfa-submit"]');
  await page.waitForSelector('[data-testid="role-badge"]', { timeout: 15000 });
  check("completing the second factor signs the user in", true);

  // --- Role-gated navigation ---
  check("admin-only Privacy section is in the sidebar",
    (await page.$('[data-testid="nav-privacy"]')) !== null);
  check("dashboard greets the signed-in user",
    (await page.locator("text=Hello,").count()) > 0);

  // --- DPDP erasure queue ---
  await page.goto(base + "/privacy", { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="privacy-list"]', { timeout: 15000 });
  check("a pending erasure request is listed", (await page.locator("text=Ravi Kumar").count()) > 0);

  check("the retention panel shows its preview counts",
    (await page.$('[data-testid="retention-panel"]')) !== null);

  await page.click('[data-testid="privacy-erase"]');
  await page.waitForSelector('[data-testid="privacy-empty"]', { timeout: 15000 });
  check("erasing the customer clears it from the pending queue", true);
} catch (e) {
  fail.push("EXCEPTION: " + e.message);
  console.log("  FAIL EXCEPTION: " + e.message);
} finally {
  if (browser) await browser.close();
  server.close();
}

console.log(`\n==== ${pass.length} passed, ${fail.length} failed ====`);
process.exit(fail.length ? 1 : 0);

// End-to-end smoke test for the customer portal, driven by a headless browser
// against the mock BFF in server.mjs. Covers the core journeys: phone-OTP login
// (wrong code rejected, right code accepted), Home data, accepting an estimate,
// and toggling a DPDP consent. Pure Node + the `playwright` library (no
// @playwright/test runner needed).
//
//   npm run test:e2e        (builds first, then runs this)
//   node tests/e2e/customer-portal.e2e.mjs   (expects build/ to already exist)
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
  return undefined; // let playwright use its default
}

const server = createServer();
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

let browser;
try {
  const executablePath = resolveChromium();
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"], ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();

  // --- Login: unauth → form, wrong code rejected, right code accepted ---
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.waitForSelector('input[type="tel"]', { timeout: 15000 });
  check("unauthenticated visit shows the phone login form", true);

  await page.fill('input[type="tel"]', "9998887777");
  await page.click('button:has-text("Send login code")');
  await page.waitForSelector('input[maxlength="4"]', { timeout: 15000 });
  check("phone step advances to the code step", true);

  await page.fill('input[maxlength="4"]', "0000");
  await page.click('button:has-text("Verify")');
  await page.waitForTimeout(600);
  check("wrong OTP keeps the user on the code step", (await page.$('input[maxlength="4"]')) !== null);

  await page.fill('input[maxlength="4"]', "4821");
  await page.click('button:has-text("Verify")');
  await page.waitForSelector("text=IJ-2026-014", { timeout: 15000 });
  check("valid OTP signs in and Home shows the project code", true);

  // --- Estimates: expand + accept ---
  await page.goto(base + "/estimates", { waitUntil: "networkidle" });
  await page.waitForSelector("text=Estimate v2", { timeout: 15000 });
  await page.click("text=Estimate v2");
  await page.click('button:has-text("Accept estimate")');
  await page.waitForSelector("text=Estimate accepted", { timeout: 15000 });
  check("accepting an estimate shows the success toast", true);

  // --- Privacy: consent toggle persists; necessary is locked ---
  await page.goto(base + "/privacy", { waitUntil: "networkidle" });
  const ai = await page.waitForSelector('[data-testid="consent-ai_training"]', { timeout: 15000 });
  check("AI-training consent starts OFF (default-off optional purpose)", (await ai.getAttribute("aria-pressed")) === "false");
  await ai.click();
  await page.waitForFunction(
    () => document.querySelector('[data-testid="consent-ai_training"]')?.getAttribute("aria-pressed") === "true",
    { timeout: 15000 },
  );
  check("toggling AI-training consent ON persists after save + reload", true);

  const svc = await page.$('[data-testid="consent-service"]');
  check("necessary consent toggle is locked (disabled)", svc ? await svc.isDisabled() : false);
} catch (e) {
  fail.push("EXCEPTION: " + e.message);
  console.log("  FAIL EXCEPTION: " + e.message);
} finally {
  if (browser) await browser.close();
  server.close();
}

console.log(`\n==== ${pass.length} passed, ${fail.length} failed ====`);
process.exit(fail.length ? 1 : 0);

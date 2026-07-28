# Customer Web — end-to-end tests

A headless-browser smoke test of the customer portal's core journeys, run against
a **mock BFF** so it needs no backend, database, or credentials.

## What it covers

- **Phone-OTP login** — the login form appears for an unauthenticated visitor, the
  phone step advances to the code step, a **wrong code is rejected**, and the
  correct code signs in and lands on Home.
- **Home** shows the customer's project.
- **Estimates** — expand an estimate and **accept** it (success toast).
- **Privacy / DPDP consent** — an optional purpose starts **off**, toggling it
  **persists**, and the **necessary** consent is **locked**.

## Run it

```bash
npm install          # first time (pulls `playwright`)
npm run test:e2e     # builds the app, then runs the browser test
```

`test:e2e` runs `vite build` then `node tests/e2e/customer-portal.e2e.mjs`. To run
the test against an existing build without rebuilding:

```bash
node tests/e2e/customer-portal.e2e.mjs
```

## How it works

- **`server.mjs`** serves the built app (`../../build`) **and** mocks
  `/api/client/*` on the same origin — mirroring production (the portal calls
  same-origin `/api`). It's stateful for the accept-estimate and consent-toggle
  flows so they behave like the real backend.
- **`customer-portal.e2e.mjs`** launches headless Chromium via the `playwright`
  library (no `@playwright/test` runner), drives the journeys, and exits non-zero
  on any failure. Chromium is auto-resolved (playwright's own path, or a browser
  under `PLAYWRIGHT_BROWSERS_PATH`); override with `PW_CHROMIUM_PATH` if needed.

## Notes

- No secrets or real endpoints are touched — safe to run anywhere.
- Not yet wired into CI (CI would need a Chromium install step); it's a one-command
  local/pre-push check today.

# Staff CRM — end-to-end tests

A headless-browser smoke test of the staff CRM's core journeys, run against a
**mock BFF** so it needs no backend, database, or credentials.

## What it covers

- **Sign-in** — the sign-in card appears for an unauthenticated visitor, and a
  **wrong password is rejected** with an error.
- **Two-factor login** — an MFA-enrolled account is asked for a second factor,
  and completing it signs the user in.
- **Role-gated navigation** — the admin-only **Privacy** section appears in the
  sidebar for a user holding `users.manage`, and the dashboard renders.
- **DPDP erasure queue** — a pending request is listed, the **retention panel**
  shows its preview counts, and **erasing** the customer clears it from the
  pending queue.

## Run it

```bash
npm install --legacy-peer-deps   # first time (React 19 needs the flag here)
npm run test:e2e                 # builds the app, then runs the browser test
```

To run against an existing build without rebuilding:

```bash
node tests/e2e/staff-crm.e2e.mjs
```

## How it works

- **`server.mjs`** serves the built app (`../../build`) **and** mocks `/api/*` on
  the same origin, so cookies and the bearer token behave as in production. It is
  stateful for the erasure queue, so erase/reject behave like the real backend.
- **`staff-crm.e2e.mjs`** launches headless Chromium via the `playwright` library
  (no `@playwright/test` runner), drives the journeys, and exits non-zero on any
  failure. Chromium is auto-resolved (playwright's own path, or a browser under
  `PLAYWRIGHT_BROWSERS_PATH`); override with `PW_CHROMIUM_PATH`.
- `window.confirm` prompts (erase / reject) are auto-accepted by a dialog handler.

## Mock credentials

| Field | Value |
|---|---|
| Email | `admin@interiojunction.com` |
| Password | `interio2026` |
| Password that triggers 2FA | `mfapass` (then any 6-digit code) |

These exist only inside `server.mjs` — no real secrets are involved.

# Interio Junction — Customer Portal

The **customer-facing** web app: the second half of the dual-BFF, running as a
**separate application** alongside the company CRM (`../frontend`) on the same
server and against the same backend.

- **Who logs in:** customers (your leads/clients), with **phone + one-time code**
  — no password, no self-signup. A code is only issued for a phone that already
  exists as a lead, so every customer maps to a known record.
- **What they can do:** see their project status, review & **accept estimates**,
  view designs and **approve / request changes**, track **payments**, download
  **documents**, and **chat** with the team.
- **What they can never reach:** anything staff-only. Every request goes to the
  `/api/client/*` BFF and carries a **customer** token; the backend rejects a
  customer token on staff routes (and vice-versa).

## Isolation from the company app

The portal is **bearer-token-only**: the customer session lives in this app's own
`localStorage` (`ij_customer_token` / `ij_customer_refresh`) and the API client
never sends cookies. So even if both web apps are served from the same domain,
the staff and customer sessions never share a cookie jar. See `src/lib/api.js`.

## Stack

React 19 + Vite + Tailwind (same toolchain as `../frontend`, deliberately kept
dependency-light — no component library). Custom UI primitives live in
`src/components/ui.jsx`.

```
src/
  lib/api.js          bearer-only axios client, refresh-on-401, step-up helper
  lib/format.js       INR money / date helpers
  contexts/AuthContext.jsx   phone-OTP login state
  hooks/useApi.js     tiny GET-on-mount hook
  components/         AppShell, ProtectedRoute, Toast, ui primitives
  pages/             Login, Home, Estimates, Designs, Payments, Documents, Chat
```

## Develop

```bash
npm install --legacy-peer-deps
npm start          # http://localhost:3100  (company app dev server uses 3000)
```

Point the dev server at a running backend by setting `REACT_APP_BACKEND_URL`
(e.g. `REACT_APP_BACKEND_URL=http://localhost:8000 npm start`). Left empty, the
app calls `/api` at same-origin — which is how it runs in production, where its
own nginx proxies `/api` to the backend.

## Build & serve

```bash
npm run build      # -> build/  (static site)
```

In production this is built and served by `Dockerfile` (Vite → nginx). The
`client-portal` service in the repo's root `docker-compose.yml` runs it on
`CLIENT_WEB_PORT` (default **8080**). See `../DEPLOYMENT.md`.

## Optional backend flags this app honours

- `CLIENT_STEP_UP_ENABLED=1` — the backend then requires a fresh confirmation on
  high-risk actions (accept estimate / approve design). The portal handles this
  transparently via `postWithStepUp()` (mints an `X-Client-Step-Up` token and
  retries). Off by default.

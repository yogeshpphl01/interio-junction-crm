# Interio Junction — Staff Web (Company CRM)

The **staff-facing** web app: the company CRM your team uses to run the business —
one half of the dual-BFF, alongside the customer portal ([`../customer-web`](../customer-web))
on the same server and against the same [`backend`](../../backend).

- **Who logs in:** your team (staff), with **email + password**, plus optional
  **MFA (TOTP)** and **passkeys**; sensitive actions can require a fresh **step-up**.
- **What they can do:** work the **pipeline**, manage **leads** and **projects**,
  schedule **site visits**, run **lead scoring** and **automations**, view
  **analytics** and the **audit log**, handle **DPDP privacy requests** and
  retention, and administer **users, roles & settings**.
- **Access is role-based:** the sidebar and every route are gated by the user's
  role/permissions (`permissions.py` on the backend). Custom roles see exactly the
  sections their toggles grant.

## Stack

React 19 + Vite + Tailwind + [sonner](https://sonner.emilkowal.ski/) toasts.
Design system: clay / bone / ink. Dependency-light; custom components, no UI kit.

## What's in `src/`

```
src/
├── pages/         one file per screen (CommandCenter, Pipeline, Projects, Leads,
│                  LeadDetail, SiteVisits, LeadScoring, Automations, Analytics,
│                  Audit, NotificationSettings, PrivacyRequests, Settings, Login)
├── components/    shared UI + chrome: AppShell (sidebar/header), ProtectedRoute,
│                  modals (ChangePassword, Security, StepUp, EditProfile, …)
├── contexts/      React context providers (AuthContext — session + permissions)
├── hooks/         reusable data/UI hooks
├── lib/           axios API client (auth refresh + step-up interceptor),
│                  formatters, constants helpers
├── constants/     role labels/colours, pipeline stages, and other static config
├── App.jsx        routes (public /login + protected AppShell with role guards)
└── index.jsx      app entry
```

## Develop

```bash
npm install
npm start          # dev server (http://localhost:3000)
npm run build      # production build -> build/
```

Point the dev server at a running backend with `REACT_APP_BACKEND_URL`
(e.g. `REACT_APP_BACKEND_URL=http://localhost:8000 npm start`). Left empty, the
app calls `/api` same-origin — which is how it runs in production, where its own
nginx proxies `/api` to the backend.

## Build & serve

In production this is built and served by `Dockerfile` (Vite → nginx). The
`frontend` service in the repo's root `docker-compose.yml` runs it on `WEB_PORT`
(default **80**). See [`../../DEPLOYMENT.md`](../../DEPLOYMENT.md).

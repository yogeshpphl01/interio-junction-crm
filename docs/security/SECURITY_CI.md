# Security CI pipeline

Three CI-time gates guard every push and pull request (P0-5 + P1-14):

| Gate | Tool | Workflow | What it catches |
|---|---|---|---|
| **Secret scanning** | gitleaks | `.github/workflows/secret-scan.yml` | committed credentials / tokens / keys (`.gitleaks.toml`) |
| **SAST** | bandit | `.github/workflows/security-ci.yml` → `sast` | insecure code patterns (CWE Top 25): command injection, weak crypto, insecure deserialization, etc. |
| **Dependency scan** | pip-audit | `.github/workflows/security-ci.yml` → `dependencies` | known-vulnerable Python packages (OSV / PyPI advisories) |

## SAST threshold

Bandit runs at **medium severity + medium confidence**. This keeps the signal
high and excludes the codebase's known-safe low/low heuristics:

- **B608** (string-built SQL) — the only SQL construction is the schema-driven
  asyncpg shim (`database.py`), which **quotes identifiers** (`_q`) and
  **parameterizes every value** (`$1…$n`). No user input reaches SQL text.
- **B105** ("password" literals) — field names and the weak-secret denylist, not
  real secrets. Real secrets are caught by gitleaks.
- **B110/B112** (try/except pass/continue) — intentional best-effort paths.

A **new** medium+ finding fails the build. Run locally:
`cd backend && bandit -r . -x ./.venv,./tests --severity-level medium --confidence-level medium`

## Dependency scan — tracked exception

`pip-audit` fails on any known-vulnerable dependency **except** a documented,
time-boxed ignore list. Currently ignored:

- **starlette 0.37.2** — `PYSEC-2026-161/248/249/1941/1943/2280/2281`. Pinned
  transitively by `fastapi==0.110.1`; the fixes are in starlette ≥ 0.40/0.47,
  which requires a **fastapi major upgrade** (app-wide blast radius — needs a
  scheduled upgrade + full re-verification). **Remove these ignores once
  fastapi/starlette are upgraded.**

Run locally: `cd backend && pip-audit -r requirements-runtime.txt`.

## Not yet wired (recommended next)

- **Flutter/Dart deps**: add `dart pub outdated` + OSV-Scanner on
  `pubspec.lock` for both apps.
- **Semgrep** rulesets (owasp-top-ten, secrets) for deeper SAST.
- **SBOM** (CycloneDX) generation + artifact retention per release.

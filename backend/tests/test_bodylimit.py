"""
Request body-size cap (API4 anti-DoS). Verifies oversized JSON is rejected with
413, that multipart uploads get their own (larger) headroom so document/Excel
uploads aren't blocked, and that BODY_LIMIT_ENABLED=0 disables the guard. Tiny
limits are injected via env so the assertions are fast. Rate limiting is turned
off here so the two anti-abuse controls are tested in isolation.

    DATABASE_URL=... JWT_SECRET=... python tests/test_bodylimit.py
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://postgres@/ijrev?host=/tmp&port=55432")
os.environ.setdefault("JWT_SECRET", "bodylimit-test-key-32-chars-minimum-abcd")
os.environ.setdefault("RUN_MIGRATIONS", "1")
os.environ.setdefault("APP_ENV", "dev")
os.environ["RATE_LIMIT_ENABLED"] = "0"          # isolate: test body caps only
os.environ["BODY_LIMIT_ENABLED"] = "1"
os.environ["MAX_JSON_BODY_BYTES"] = "500"       # tiny JSON cap for the test
os.environ["MAX_BODY_BYTES"] = "2000"           # tiny upload cap for the test
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from server import app

passed, failed = [], []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def main():
    with TestClient(app) as c:
        # Oversized JSON body → 413 (guard runs before routing).
        big = c.post("/api/auth/login", json={"email": "a@b.c", "password": "P" * 600})
        check("oversized JSON body → 413", big.status_code == 413)

        # Normal small JSON → allowed through to the handler (401 bad creds, not 413).
        small = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"})
        check("normal small JSON passes the guard", small.status_code == 401)

        # Small multipart upload → not blocked by the JSON cap (uses the upload cap).
        small_up = c.post("/api/documents", files={"file": ("x.bin", b"A" * 200)}, data={"project_id": "p", "type": "3D Render"})
        check("small multipart upload not blocked by JSON cap", small_up.status_code != 413)

        # Oversized multipart upload (> upload cap) → 413.
        big_up = c.post("/api/documents", files={"file": ("x.bin", b"A" * 2500)}, data={"project_id": "p", "type": "3D Render"})
        check("oversized multipart upload → 413", big_up.status_code == 413)

        # Kill switch: disabled → oversized JSON passes.
        os.environ["BODY_LIMIT_ENABLED"] = "0"
        off = c.post("/api/auth/login", json={"email": "a@b.c", "password": "P" * 600})
        check("disabled guard lets the oversized JSON through", off.status_code != 413)
        os.environ["BODY_LIMIT_ENABLED"] = "1"

    print(f"\n==== {len(passed)} passed, {len(failed)} failed ====")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()

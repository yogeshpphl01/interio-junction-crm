"""
API4 anti-abuse rate limiting on the auth/OTP endpoints (backend/ratelimit.py).

Verifies the per-IP sliding window trips a 429 (+Retry-After) past the limit,
that buckets are independent, and that RATE_LIMIT_ENABLED=0 disables it. Small
limits are injected via env overrides so the assertions are fast and independent
of the production defaults.

    DATABASE_URL=... JWT_SECRET=... python tests/test_ratelimit.py
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://postgres@/ijrev?host=/tmp&port=55432")
os.environ.setdefault("JWT_SECRET", "ratelimit-test-key-32-chars-minimum-abcd")
os.environ.setdefault("RUN_MIGRATIONS", "1")
os.environ.setdefault("APP_ENV", "dev")
# Tiny limits so the test trips quickly: bucket -> "MAX/WINDOW_SECONDS".
os.environ["RATE_LIMIT_ENABLED"] = "1"
os.environ["RATE_LIMIT_CLIENT_REQUEST_OTP"] = "3/600"
os.environ["RATE_LIMIT_AUTH_LOGIN"] = "3/300"
os.environ["RATE_LIMIT_CLIENT_VERIFY_OTP"] = "50/600"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
import ratelimit
from server import app

passed, failed = [], []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def main():
    with TestClient(app) as c:
        # request-otp: 3 allowed, 4th throttled
        ratelimit.reset()
        first3 = [c.post("/api/client/auth/request-otp", json={"phone": "9800000001"}).status_code for _ in range(3)]
        check("first 3 request-otp calls allowed", all(s == 200 for s in first3))
        r4 = c.post("/api/client/auth/request-otp", json={"phone": "9800000001"})
        check("4th request-otp is 429", r4.status_code == 429)
        check("429 carries a numeric Retry-After header", r4.headers.get("Retry-After", "").isdigit())

        # buckets are independent: verify-otp not blocked by request-otp's counter
        rv = c.post("/api/client/auth/verify-otp", json={"phone": "9800000001", "code": "0000"})
        check("verify-otp bucket independent of request-otp", rv.status_code != 429)

        # staff login: 3 allowed (401 bad creds), 4th throttled
        ratelimit.reset()
        logins = [c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code for _ in range(3)]
        check("first 3 logins allowed (401, not throttled)", all(s == 401 for s in logins))
        check("4th login is 429", c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code == 429)

        # kill switch
        os.environ["RATE_LIMIT_ENABLED"] = "0"
        ratelimit.reset()
        off = [c.post("/api/client/auth/request-otp", json={"phone": "9800000002"}).status_code for _ in range(6)]
        check("disabled: 6 rapid calls all allowed", all(s == 200 for s in off))
        os.environ["RATE_LIMIT_ENABLED"] = "1"

    print(f"\n==== {len(passed)} passed, {len(failed)} failed ====")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()

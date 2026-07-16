"""
Authorization test suite — BOLA, BFLA, dual-BFF and unauthenticated access
(OWASP API1 / API5; the in-process equivalent of a DAST authZ sweep). Runs the
real app via TestClient against Postgres.

    DATABASE_URL=... JWT_SECRET=... python tests/test_authz.py
"""
import os
import sys
import uuid
import asyncio
import datetime

os.environ.setdefault("DATABASE_URL", "postgresql://postgres@/ijrev?host=/tmp&port=55432")
os.environ.setdefault("JWT_SECRET", "authz-test-key-32-chars-minimum-length-x")
os.environ.setdefault("RUN_MIGRATIONS", "1")
os.environ.setdefault("APP_ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
import bcrypt
from fastapi.testclient import TestClient
from server import app
import auth_utils

DSN = os.environ["DATABASE_URL"]
PWD = "interio2026"
passed, failed = [], []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def _run(coro):
    async def _():
        conn = await asyncpg.connect(DSN)
        try:
            return await coro(conn)
        finally:
            await conn.close()
    return asyncio.run(_())


def seed():
    async def _(conn):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        h = bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()
        ids = {}
        # low-privilege staff (sales) + a valid admin for the negative-control
        await conn.execute("UPDATE users SET password_hash=$1,is_active=true,token_version=0,role='sales' WHERE email='sales@interiojunction.com'", h)
        ids["sales_id"] = (await conn.fetchrow("SELECT id FROM users WHERE email='sales@interiojunction.com'"))["id"]
        ids["admin_id"] = (await conn.fetchrow("SELECT id FROM users WHERE email='admin@interiojunction.com'"))["id"]
        # two customers, each with their own project + a client-visible document
        for tag in ("c1", "c2"):
            cid = f"authz-{tag}-" + uuid.uuid4().hex[:8]
            pid = f"authz-proj-{tag}-" + uuid.uuid4().hex[:8]
            phone = "+91 9" + uuid.uuid4().int.__str__()[:9]
            await conn.execute("INSERT INTO projects (id,project_code,created_at) VALUES ($1,$2,$3)", pid, "IJ-"+uuid.uuid4().hex[:6], now)
            await conn.execute("INSERT INTO customers (id,phone,full_name,is_active,token_version,created_at) VALUES ($1,$2,$3,true,0,$4)", cid, phone, tag.upper(), now)
            await conn.execute("INSERT INTO leads (id,full_name,phone,stage,status,project_id,customer_id,created_at,updated_at) VALUES ($1,$2,$3,4,'Active',$4,$5,$6,$6)",
                               str(uuid.uuid4()), tag.upper(), phone, pid, cid, now)
            doc = f"authz-doc-{tag}-" + uuid.uuid4().hex[:8]
            await conn.execute("INSERT INTO documents (id,project_id,type,storage_path,original_filename,content_type,size,uploaded_by,is_deleted,created_at) VALUES ($1,$2,'3D Render',$3,'r.png','image/png',10,$4,false,$5)",
                               doc, pid, f"path/{doc}.png", ids["admin_id"], now)
            ids[tag] = {"cid": cid, "pid": pid, "phone": phone, "doc": doc}
        return ids
    return _run(_)


def main():
    with TestClient(app) as c:
        ids = seed()
        H = lambda t: {"Authorization": f"Bearer {t}"}
        c1_tok = auth_utils.create_customer_access_token(ids["c1"]["cid"], ids["c1"]["phone"], tv=0)
        c2_tok = auth_utils.create_customer_access_token(ids["c2"]["cid"], ids["c2"]["phone"], tv=0)
        sales = c.post("/api/auth/login", json={"email": "sales@interiojunction.com", "password": PWD}).json().get("access_token")

        print("[BOLA] a customer cannot reach another customer's objects")
        check("C1 signed-url for OWN doc -> 200",
              c.get(f"/api/client/documents/{ids['c1']['doc']}/signed-url", headers=H(c1_tok)).status_code == 200)
        check("C1 signed-url for C2's doc -> 404",
              c.get(f"/api/client/documents/{ids['c2']['doc']}/signed-url", headers=H(c1_tok)).status_code == 404)
        me1 = c.get("/api/client/me", headers=H(c1_tok)).json().get("customer", {})
        check("client/me returns the caller's own record", me1.get("id") == ids["c1"]["cid"])
        # C1's document listing must not contain C2's doc
        docs1 = c.get("/api/client/documents", headers=H(c1_tok)).json().get("documents", [])
        check("C1 listing excludes C2's document", all(d["id"] != ids["c2"]["doc"] for d in docs1))

        print("\n[BFLA] low-privilege staff cannot hit privileged functions")
        check("sales POST /users (users.manage) -> 403",
              c.post("/api/users", headers=H(sales), json={"email": "x@y.com", "full_name": "X", "role": "sales"}).status_code == 403)
        check("sales GET /audit (audit.view) -> 403",
              c.get("/api/audit", headers=H(sales)).status_code == 403)
        check("sales GET /audit/verify-chain -> 403",
              c.get("/api/audit/verify-chain", headers=H(sales)).status_code == 403)
        check("sales DELETE /users/{admin} (users.delete) -> 403",
              c.delete(f"/api/users/{ids['admin_id']}", headers=H(sales)).status_code == 403)
        check("sales POST /erasure-requests list (users.manage) -> 403",
              c.get("/api/erasure-requests", headers=H(sales)).status_code == 403)

        print("\n[dual-BFF] token families are mutually rejected")
        check("customer token on staff /auth/me -> 401", c.get("/api/auth/me", headers=H(c1_tok)).status_code == 401)
        check("staff token on customer /client/me -> 401", c.get("/api/client/me", headers=H(sales)).status_code == 401)

        print("\n[unauth] no token is rejected")
        check("no token on /auth/me -> 401", c.get("/api/auth/me").status_code == 401)
        check("no token on /client/me -> 401", c.get("/api/client/me").status_code == 401)
        check("no token on /users -> 401", c.get("/api/users").status_code == 401)
        # tampered token
        check("garbage bearer -> 401", c.get("/api/auth/me", headers=H("a.b.c")).status_code == 401)

        # cleanup
        _run(lambda conn: conn.execute("DELETE FROM customers WHERE id = ANY($1::text[])", [ids["c1"]["cid"], ids["c2"]["cid"]]))

    print(f"\n==== {len(passed)} passed, {len(failed)} failed ====")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()

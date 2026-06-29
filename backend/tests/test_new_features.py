"""Tests for new features (iteration 2):
- Lost/Won/On-hold close workflow
- Audit log endpoints
- Notification settings + SMTP test
- Regression: refactored backend endpoint contracts preserved
"""
import os
import io
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
PWD = "interio2026"

CREDS = {
    "admin": "admin@interiojunction.com",
    "sales": "sales@interiojunction.com",
    "designer": "designer@interiojunction.com",
    "supervisor": "supervisor@interiojunction.com",
}


def _login(email):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login fail {email}: {r.text}"
    body = r.json()
    s.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    return s, body


@pytest.fixture(scope="module")
def admin():
    return _login(CREDS["admin"])


@pytest.fixture(scope="module")
def sales():
    return _login(CREDS["sales"])


@pytest.fixture(scope="module")
def designer():
    return _login(CREDS["designer"])


@pytest.fixture(scope="module")
def supervisor():
    return _login(CREDS["supervisor"])


# ============ Close Lead Workflow ============
class TestCloseLeadWorkflow:
    def _pick_lead(self, s, prefer_with_project=False):
        leads = s.get(f"{API}/leads").json()
        active = [l for l in leads if l.get("status") == "Active"]
        if prefer_with_project:
            with_p = [l for l in active if l.get("project_id")]
            if with_p:
                return with_p[0]
        return active[0] if active else leads[0]

    def test_lost_without_reason_400(self, admin):
        s, _ = admin
        lead = self._pick_lead(s)
        r = s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Lost", "reason": ""})
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"

    def test_lost_with_reason_persists(self, admin):
        s, _ = admin
        lead = self._pick_lead(s)
        r = s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Lost", "reason": "Budget mismatch TEST"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "Lost"
        assert j.get("lost_reason") == "Budget mismatch TEST"
        assert j.get("closed_at") is not None
        # verify persistence
        detail = s.get(f"{API}/leads/{lead['id']}").json()
        assert detail["status"] == "Lost"
        assert detail["lost_reason"] == "Budget mismatch TEST"
        # activity row created
        assert any("Lost" in a.get("summary", "") for a in detail.get("activities", []))

    def test_reopen_clears_reasons(self, admin):
        s, _ = admin
        # find the lost lead from previous test
        leads = s.get(f"{API}/leads", params={"status": "Lost"}).json()
        if not leads:
            pytest.skip("no lost lead available")
        lead = leads[0]
        r = s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Active", "reason": ""})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "Active"
        assert j.get("lost_reason") in (None, "")
        assert j.get("closed_at") in (None, "")

    def test_won_with_value_sets_contract(self, admin):
        s, _ = admin
        lead = self._pick_lead(s, prefer_with_project=True)
        if not lead.get("project_id"):
            pytest.skip("no lead with project")
        r = s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Won", "reason": "Closed deal TEST", "won_value": 1234567.0})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "Won"
        assert j.get("won_reason") == "Closed deal TEST"
        assert j.get("won_value") == 1234567.0
        # project should reflect contract_value + signed_off
        proj = j.get("project") or {}
        assert proj.get("signed_off") is True
        assert float(proj.get("contract_value")) == 1234567.0
        # reopen
        s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Active", "reason": ""})

    def test_on_hold_persists(self, admin):
        s, _ = admin
        lead = self._pick_lead(s)
        r = s.post(f"{API}/leads/{lead['id']}/close", json={"status": "On-hold", "reason": "Awaiting client TEST"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "On-hold"
        assert j.get("hold_reason") == "Awaiting client TEST"
        s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Active", "reason": ""})

    def test_designer_cannot_close(self, designer, admin):
        d, _ = designer
        a, _ = admin
        leads = a.get(f"{API}/leads").json()
        # use any lead id; even if designer can't see it, expect 403 or 404
        lead_id = leads[0]["id"]
        r = d.post(f"{API}/leads/{lead_id}/close", json={"status": "Lost", "reason": "x"})
        assert r.status_code in (403, 404), f"expected 403/404 got {r.status_code} {r.text}"

    def test_supervisor_cannot_close(self, supervisor, admin):
        sup, _ = supervisor
        a, _ = admin
        leads = a.get(f"{API}/leads").json()
        lead_id = leads[0]["id"]
        r = sup.post(f"{API}/leads/{lead_id}/close", json={"status": "Lost", "reason": "x"})
        assert r.status_code in (403, 404)

    def test_close_logs_audit(self, admin):
        s, _ = admin
        lead = self._pick_lead(s)
        s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Lost", "reason": "Audit test TEST"})
        r = s.get(f"{API}/audit", params={"action": "lead.closed_lost", "target_id": lead["id"], "limit": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert any(row.get("target_id") == lead["id"] for row in body["rows"])
        s.post(f"{API}/leads/{lead['id']}/close", json={"status": "Active", "reason": ""})


# ============ Audit Log ============
class TestAuditLog:
    def test_admin_can_list(self, admin):
        s, _ = admin
        r = s.get(f"{API}/audit", params={"limit": 10})
        assert r.status_code == 200
        j = r.json()
        for k in ("total", "limit", "offset", "rows"):
            assert k in j
        assert isinstance(j["rows"], list)
        # ensure no _id leaks
        assert all("_id" not in row for row in j["rows"])

    def test_non_admin_forbidden(self, sales, designer, supervisor):
        for role_pair in (sales, designer, supervisor):
            s, _ = role_pair
            r = s.get(f"{API}/audit", params={"limit": 5})
            assert r.status_code == 403, f"got {r.status_code}"

    def test_actions_endpoint(self, admin):
        s, _ = admin
        r = s.get(f"{API}/audit/actions")
        assert r.status_code == 200
        j = r.json()
        assert "actions" in j and isinstance(j["actions"], list)

    def test_filter_by_action(self, admin):
        s, _ = admin
        # Generate a lead.updated row first
        leads = s.get(f"{API}/leads").json()
        if leads:
            s.patch(f"{API}/leads/{leads[0]['id']}", json={"notes": "audit filter TEST"})
        r = s.get(f"{API}/audit", params={"action": "lead.updated", "limit": 5})
        assert r.status_code == 200
        j = r.json()
        for row in j["rows"]:
            assert row["action"] == "lead.updated"

    def test_pagination(self, admin):
        s, _ = admin
        r1 = s.get(f"{API}/audit", params={"limit": 2, "offset": 0}).json()
        r2 = s.get(f"{API}/audit", params={"limit": 2, "offset": 2}).json()
        # if enough rows, the two pages should differ
        if r1["total"] >= 4:
            # Use action+target_id+actor_id combination since created_at can collide
            sig1 = [(r.get("action"), r.get("target_id"), r.get("actor_id"), r.get("created_at")) for r in r1["rows"]]
            sig2 = [(r.get("action"), r.get("target_id"), r.get("actor_id"), r.get("created_at")) for r in r2["rows"]]
            # at least one row must differ between page 1 and page 2
            assert set(sig1) != set(sig2) or len(sig1) != len(sig2)

    def test_search_q(self, admin):
        s, _ = admin
        r = s.get(f"{API}/audit", params={"q": "lead", "limit": 5})
        assert r.status_code == 200

    def test_stage_move_creates_audit(self, admin):
        s, _ = admin
        # find any lead and move it (will log audit either way)
        leads = s.get(f"{API}/leads").json()
        target = next((l for l in leads if l.get("stage") and l["stage"] < 6), None)
        if not target:
            pytest.skip("no lead to move")
        cur = target["stage"]
        nxt = cur + 1 if cur < 6 else cur - 1
        # try; allow 409 (gate blocked) — audit still triggers only on success
        mv = s.post(f"{API}/leads/{target['id']}/move", json={"to_stage": nxt, "override": True})
        if mv.status_code == 200:
            r = s.get(f"{API}/audit", params={"action": "lead.stage_changed", "target_id": target["id"], "limit": 3})
            assert r.status_code == 200
            assert r.json()["total"] >= 1


# ============ Notifications ============
class TestNotifications:
    def test_get_settings_admin(self, admin):
        s, _ = admin
        r = s.get(f"{API}/notifications/settings")
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("enabled", "admin_email", "from_email", "events", "configured", "provider", "smtp_host", "smtp_user"):
            assert k in j, f"missing {k}"
        assert j["provider"] == "smtp"

    def test_get_settings_forbidden(self, sales, designer, supervisor):
        for pair in (sales, designer, supervisor):
            s, _ = pair
            r = s.get(f"{API}/notifications/settings")
            assert r.status_code == 403

    def test_save_settings_persists(self, admin):
        s, _ = admin
        payload = {
            "enabled": True,
            "admin_email": "care@interiojunction.in",
            "events": {"sla_breach_48h": True, "escalate_hot_lead": False, "notify_designer_revision": True},
        }
        r = s.post(f"{API}/notifications/settings", json=payload)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["enabled"] is True
        assert j["admin_email"] == "care@interiojunction.in"
        assert j["events"]["escalate_hot_lead"] is False
        # reload and verify persistence
        r2 = s.get(f"{API}/notifications/settings").json()
        assert r2["enabled"] is True
        assert r2["admin_email"] == "care@interiojunction.in"
        assert r2["events"]["escalate_hot_lead"] is False

    def test_save_settings_forbidden(self, sales):
        s, _ = sales
        r = s.post(f"{API}/notifications/settings", json={"enabled": False})
        assert r.status_code == 403

    def test_test_email_forbidden(self, sales):
        s, _ = sales
        r = s.post(f"{API}/notifications/test", json={"to": "care@interiojunction.in"})
        assert r.status_code == 403

    def test_test_email_admin(self, admin):
        s, _ = admin
        # Send a single real email to allowed address (per instructions)
        r = s.post(f"{API}/notifications/test", json={"to": "care@interiojunction.in"}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "ok" in j and "info" in j


# ============ Regression: refactored endpoints contracts ============
class TestRegression:
    def test_meta(self, admin):
        s, _ = admin
        r = s.get(f"{API}/meta")
        assert r.status_code == 200
        assert len(r.json()["stages"]) == 9

    def test_leads_list_no_id_leak(self, admin):
        s, _ = admin
        leads = s.get(f"{API}/leads").json()
        assert all("_id" not in l for l in leads)

    def test_scoring(self, admin):
        s, _ = admin
        r = s.get(f"{API}/scoring")
        assert r.status_code == 200
        assert "weights" in r.json()

    def test_get_weights(self, admin):
        s, _ = admin
        r = s.get(f"{API}/scoring/weights")
        assert r.status_code == 200

    def test_automations_list(self, admin):
        s, _ = admin
        r = s.get(f"{API}/automations")
        assert r.status_code == 200
        assert len(r.json()) == 4

    def test_analytics(self, admin):
        s, _ = admin
        r = s.get(f"{API}/analytics/command-center")
        assert r.status_code == 200
        assert r.json()["scope"] == "company"

    def test_document_roundtrip(self, admin):
        s, _ = admin
        leads = s.get(f"{API}/leads").json()
        proj_lead = next((l for l in leads if l.get("project_id")), None)
        if not proj_lead:
            pytest.skip("no project lead")
        files = {"file": ("regress.txt", io.BytesIO(b"REGRESS TEST CONTENT"), "text/plain")}
        data = {"project_id": proj_lead["project_id"], "type": "Other"}
        r = s.post(f"{API}/documents", data=data, files=files, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert "id" in doc and "_id" not in doc
        dl = s.get(f"{API}/documents/{doc['id']}/download", timeout=20)
        assert dl.status_code == 200
        assert b"REGRESS TEST CONTENT" in dl.content
        # audit for doc upload + download should exist
        a1 = s.get(f"{API}/audit", params={"action": "document.uploaded", "target_id": doc["id"]}).json()
        assert a1["total"] >= 1

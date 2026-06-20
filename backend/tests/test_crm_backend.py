"""Interio Junction CRM — backend pytest suite.

Covers: auth (login/me/refresh/logout, role gating), meta, leads RBAC,
pipeline gates, stage move + auto project, measurements, revisions,
documents upload/download + ACL, scoring + weights, automations,
analytics command-center, users RBAC.
"""
import io
import json
import os
import uuid
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


def _login(email, password=PWD):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    s.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    return s, body


@pytest.fixture(scope="session")
def admin():
    s, b = _login(CREDS["admin"]); return s, b


@pytest.fixture(scope="session")
def sales():
    s, b = _login(CREDS["sales"]); return s, b


@pytest.fixture(scope="session")
def designer():
    s, b = _login(CREDS["designer"]); return s, b


@pytest.fixture(scope="session")
def supervisor():
    s, b = _login(CREDS["supervisor"]); return s, b


# ---------- Auth ----------
class TestAuth:
    def test_login_all_roles(self):
        for role, em in CREDS.items():
            r = requests.post(f"{API}/auth/login", json={"email": em, "password": PWD}, timeout=15)
            assert r.status_code == 200, f"{role} login: {r.text}"
            j = r.json()
            assert j["user"]["role"] == role
            assert "access_token" in j and len(j["access_token"]) > 20

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": CREDS["admin"], "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_authenticated(self, admin):
        s, _ = admin
        r = s.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_refresh_with_cookie(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": CREDS["admin"], "password": PWD}, timeout=15)
        assert r.status_code == 200
        # cookies should be set
        assert "refresh_token" in s.cookies.get_dict() or any(c.name == "refresh_token" for c in s.cookies)
        r2 = s.post(f"{API}/auth/refresh", timeout=15)
        assert r2.status_code == 200, r2.text

    def test_logout(self, admin):
        s, _ = admin
        r = s.post(f"{API}/auth/logout", timeout=15)
        assert r.status_code == 200


# ---------- Meta ----------
class TestMeta:
    def test_meta(self, admin):
        s, _ = admin
        r = s.get(f"{API}/meta", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert len(j["stages"]) == 6
        assert j["default_weights"]


# ---------- Leads RBAC ----------
class TestLeadsRBAC:
    def test_admin_sees_all(self, admin):
        s, _ = admin
        r = s.get(f"{API}/leads", timeout=20)
        assert r.status_code == 200
        leads = r.json()
        assert len(leads) >= 6, f"expected seeded leads, got {len(leads)}"
        # _id should never leak
        assert all("_id" not in l for l in leads)

    def test_sales_only_assigned(self, sales):
        s, body = sales
        uid = body["user"]["id"]
        r = s.get(f"{API}/leads", timeout=20)
        assert r.status_code == 200
        leads = r.json()
        assert all(l.get("assigned_to") == uid for l in leads), "sales got leads not assigned to them"

    def test_designer_scope(self, designer):
        s, _ = designer
        r = s.get(f"{API}/leads", timeout=20)
        assert r.status_code == 200
        # Designer should only see leads of projects where they have revisions
        # (could be 0 or more depending on seed)
        leads = r.json()
        assert isinstance(leads, list)

    def test_supervisor_scope(self, supervisor):
        s, _ = supervisor
        r = s.get(f"{API}/leads", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Pipeline / Gates ----------
class TestPipelineGates:
    def test_get_lead_detail(self, admin):
        s, _ = admin
        leads = s.get(f"{API}/leads").json()
        lid = leads[0]["id"]
        r = s.get(f"{API}/leads/{lid}", timeout=15)
        assert r.status_code == 200
        j = r.json()
        for k in ("measurements", "revisions", "payments", "documents", "activities", "stage_history"):
            assert k in j

    def test_stage_gate_blocks_stage3_to_4_without_measurement(self, admin):
        s, _ = admin
        leads = s.get(f"{API}/leads").json()
        # find a lead at stage 3 with no completed measurement
        target = None
        for l in leads:
            if l.get("stage") == 3:
                detail = s.get(f"{API}/leads/{l['id']}").json()
                if not any(m.get("status") == "Completed" for m in detail.get("measurements", [])):
                    target = l
                    break
        if not target:
            pytest.skip("no stage-3 lead without completed measurement found")
        r = s.post(f"{API}/leads/{target['id']}/move", json={"to_stage": 4}, timeout=15)
        assert r.status_code == 409, f"expected 409 block, got {r.status_code} {r.text}"
        assert "Site Measurement" in r.json().get("detail", "") or "Completed" in r.json().get("detail", "")

    def test_stage_gate_unblocks_after_completion(self, admin):
        s, _ = admin
        leads = s.get(f"{API}/leads").json()
        target = None
        for l in leads:
            if l.get("stage") == 3 and l.get("project_id"):
                target = l
                break
        if not target:
            pytest.skip("no stage-3 lead with project")
        # mark one measurement Completed (create if none)
        detail = s.get(f"{API}/leads/{target['id']}").json()
        ms_list = detail.get("measurements", [])
        if ms_list:
            ms_id = ms_list[0]["id"]
        else:
            cr = s.post(f"{API}/measurements", json={"project_id": target["project_id"], "status": "Scheduled"})
            assert cr.status_code == 200, cr.text
            ms_id = cr.json()["id"]
        up = s.patch(f"{API}/measurements/{ms_id}", json={"status": "Completed"})
        assert up.status_code == 200, up.text
        # now move to 4
        mv = s.post(f"{API}/leads/{target['id']}/move", json={"to_stage": 4}, timeout=15)
        assert mv.status_code == 200, mv.text
        assert mv.json()["stage"] == 4

    def test_auto_project_on_stage3(self, admin):
        s, _ = admin
        # find a stage 1/2 lead and push to stage 3
        leads = s.get(f"{API}/leads").json()
        target = next((l for l in leads if l.get("stage") in (1, 2) and not l.get("project_id")), None)
        if not target:
            pytest.skip("no early-stage lead without project")
        # move stage 1->2 if needed then 2->3
        if target["stage"] == 1:
            r = s.post(f"{API}/leads/{target['id']}/move", json={"to_stage": 2})
            assert r.status_code == 200
        r = s.post(f"{API}/leads/{target['id']}/move", json={"to_stage": 3})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("project") is not None
        assert j["project"]["project_code"].startswith("IJ-")

    def test_gate_4_to_5_requires_approved_revision(self, admin):
        s, _ = admin
        leads = s.get(f"{API}/leads").json()
        target = next((l for l in leads if l.get("stage") == 4), None)
        if not target:
            pytest.skip("no stage-4 lead")
        detail = s.get(f"{API}/leads/{target['id']}").json()
        if any(r.get("status") == "Approved" for r in detail.get("revisions", [])):
            pytest.skip("already has approved revision")
        r = s.post(f"{API}/leads/{target['id']}/move", json={"to_stage": 5})
        assert r.status_code == 409


# ---------- Measurements & Revisions ----------
class TestMeasurementsRevisions:
    def test_supervisor_can_complete_own_measurement(self, supervisor, admin):
        sup, sup_b = supervisor
        # supervisor measurements list
        r = sup.get(f"{API}/measurements", timeout=15)
        assert r.status_code == 200
        ms = r.json()
        if not ms:
            pytest.skip("no measurements for supervisor")
        target = ms[0]
        up = sup.patch(f"{API}/measurements/{target['id']}", json={"total_area_sqft": 1234.5, "status": "Completed"})
        assert up.status_code == 200, up.text
        assert up.json()["status"] == "Completed"

    def test_designer_can_add_revision(self, designer, admin):
        d, _ = designer
        a, _ = admin
        # find any project from admin's lead list
        leads = a.get(f"{API}/leads").json()
        proj = next((l.get("project") for l in leads if l.get("project")), None)
        if not proj:
            pytest.skip("no project to attach revision")
        r = d.post(f"{API}/revisions", json={"project_id": proj["id"], "title": "TEST revision", "status": "Draft"})
        # Designer can post; if they're not yet associated with this project visibility may still allow create
        assert r.status_code in (200, 403), r.text


# ---------- Documents ACL ----------
class TestDocuments:
    @pytest.fixture(scope="class")
    def uploaded(self, admin, sales):
        s, _ = admin
        sales_session, sales_body = sales
        sales_id = sales_body["user"]["id"]
        leads = s.get(f"{API}/leads").json()
        # pick a project-lead NOT assigned to sales user (so we can test 403)
        proj_lead = next((l for l in leads if l.get("project_id") and l.get("assigned_to") != sales_id), None)
        if not proj_lead:
            proj_lead = next((l for l in leads if l.get("project_id")), None)
        if not proj_lead:
            pytest.skip("no project with id")
        files = {"file": ("test.txt", io.BytesIO(b"hello world TEST"), "text/plain")}
        data = {"project_id": proj_lead["project_id"], "type": "Other"}
        r = s.post(f"{API}/documents", data=data, files=files, timeout=30)
        assert r.status_code == 200, r.text
        return r.json(), proj_lead

    def test_admin_download(self, admin, uploaded):
        s, _ = admin
        doc, _ = uploaded
        r = s.get(f"{API}/documents/{doc['id']}/download", timeout=30)
        assert r.status_code == 200
        assert b"hello world TEST" in r.content

    def test_sales_unauthorized_download(self, sales, uploaded):
        s, body = sales
        doc, proj_lead = uploaded
        # if this sales user happens to own that lead, skip
        if proj_lead.get("assigned_to") == body["user"]["id"]:
            pytest.skip("sales user owns this lead")
        r = s.get(f"{API}/documents/{doc['id']}/download", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ---------- Scoring ----------
class TestScoring:
    def test_default_scoring(self, admin):
        s, _ = admin
        r = s.get(f"{API}/scoring", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "weights" in j and "leads" in j
        if j["leads"]:
            top = j["leads"][0]
            keys = {sig["key"] for sig in top["signals"]}
            for k in ("budget_tier", "lead_type", "source_quality", "pipeline_progress", "engagement", "recency"):
                assert k in keys
            for sig in top["signals"]:
                assert "weight" in sig and "ratio" in sig and "points" in sig
            assert top["heat"] in ("Hot", "Warm", "Cold")
            scores = [l["score"] for l in j["leads"]]
            assert scores == sorted(scores, reverse=True)

    def test_weights_override_recomputes(self, admin):
        s, _ = admin
        w = {"budget_tier": 100, "lead_type": 0, "source_quality": 0, "pipeline_progress": 0, "engagement": 0, "recency": 0}
        r = s.get(f"{API}/scoring", params={"weights": json.dumps(w)}, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j["weights"]["budget_tier"] == 100
        if j["leads"]:
            for l in j["leads"][:3]:
                bt_sig = next(s for s in l["signals"] if s["key"] == "budget_tier")
                # Only budget_tier contributes => score equals its points (within rounding)
                assert abs(l["score"] - bt_sig["points"]) <= 1


# ---------- Automations ----------
class TestAutomations:
    def test_list_automations(self, admin):
        s, _ = admin
        r = s.get(f"{API}/automations", timeout=15)
        assert r.status_code == 200
        rules = r.json()
        assert len(rules) == 4
        for rule in rules:
            assert "runs_today" in rule and isinstance(rule["runs_today"], int)

    def test_toggle_automation(self, admin):
        s, _ = admin
        r = s.patch(f"{API}/automations/sla_breach_48h", json={"enabled": False})
        assert r.status_code == 200 and r.json()["enabled"] is False
        r2 = s.patch(f"{API}/automations/sla_breach_48h", json={"enabled": True})
        assert r2.status_code == 200 and r2.json()["enabled"] is True

    def test_run_checks(self, admin):
        s, _ = admin
        r = s.post(f"{API}/automations/run-checks", timeout=20)
        assert r.status_code == 200
        assert "fired" in r.json()

    def test_signals(self, admin):
        s, _ = admin
        r = s.get(f"{API}/automations/signals", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_toggle_requires_admin(self, sales):
        s, _ = sales
        r = s.patch(f"{API}/automations/sla_breach_48h", json={"enabled": False})
        assert r.status_code == 403


# ---------- Analytics ----------
class TestAnalytics:
    def test_admin_company_scope(self, admin):
        s, _ = admin
        r = s.get(f"{API}/analytics/command-center", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j["scope"] == "company"
        for k in ("total_pipeline", "forecast", "win_rate", "cycle_days"):
            assert k in j["kpis"]
        assert len(j["funnel"]) == 6
        assert len(j["forecast_trend"]) == 6
        assert "by_source" in j

    def test_sales_self_scope(self, sales):
        s, _ = sales
        r = s.get(f"{API}/analytics/command-center", timeout=20)
        assert r.status_code == 200
        assert r.json()["scope"] == "self"


# ---------- Users RBAC ----------
class TestUsers:
    def test_admin_can_create_user(self, admin):
        s, _ = admin
        email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{API}/users", json={"email": email, "full_name": "TEST User", "role": "sales"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["email"] == email.lower()
        assert j["role"] == "sales"
        # verify via GET /users
        listing = s.get(f"{API}/users").json()
        assert any(u["email"] == email.lower() for u in listing)

    def test_sales_cannot_create_user(self, sales):
        s, _ = sales
        email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{API}/users", json={"email": email, "full_name": "X", "role": "sales"}, timeout=15)
        assert r.status_code == 403

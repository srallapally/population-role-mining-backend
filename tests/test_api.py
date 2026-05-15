# backend/tests/test_api.py
import time
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

ANALYST = "analyst@example.com"
HEADERS = {"X-Analyst-Id": ANALYST}
FILTER = {"JobCode": ["JC10", "JC20"]}


# --- Columns ---

def test_get_columns():
    resp = client.get("/api/v1/columns")
    assert resp.status_code == 200
    cols = resp.json()["columns"]
    assert "JobCode" in cols
    assert "usr_id" not in cols


# --- Session creation ---

def test_create_session_201():
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "sessionId" in body
    assert body["status"] == "pending"


def test_create_session_defaults_resolved():
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "roleType": "job_roles"},
        headers=HEADERS,
    )
    sid = resp.json()["sessionId"]
    session = client.get(f"/api/v1/sessions/{sid}").json()
    params = session["parameters"]
    assert params["universalThreshold"] == 0.90
    assert params["coverageThreshold"] == 0.80
    assert params["noiseFilterValue"] == max(2, int(30 * 0.80) - 1)


def test_create_session_override_persisted():
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "roleType": "job_roles", "universalThreshold": 0.75},
        headers=HEADERS,
    )
    sid = resp.json()["sessionId"]
    session = client.get(f"/api/v1/sessions/{sid}").json()
    assert session["parameters"]["universalThreshold"] == 0.75


def test_create_session_missing_analyst_400():
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "roleType": "job_roles"},
    )
    assert resp.status_code == 400


def test_create_session_empty_filter_400():
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": {}, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_create_session_invalid_filter_key_400():
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": {"nonexistent_column": "x"}, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_create_session_active_limit_429(monkeypatch):
    import config

    monkeypatch.setattr(config, "MAX_ACTIVE_SESSIONS", 1)
    _create_session()
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "minGroupSize": 3, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 429


def test_create_session_terminal_session_does_not_count_against_active_limit(monkeypatch):
    import config
    from data import store

    monkeypatch.setattr(config, "MAX_ACTIVE_SESSIONS", 1)
    sid = _create_session()
    session = store.get_session(sid)
    session["status"] = "complete"
    store.put_session(session)

    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "minGroupSize": 3, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 201


def test_create_session_total_limit_429(monkeypatch):
    import config
    from data import store

    monkeypatch.setattr(config, "MAX_ACTIVE_SESSIONS", 10)
    monkeypatch.setattr(config, "MAX_TOTAL_SESSIONS", 1)
    sid = _create_session()
    session = store.get_session(sid)
    session["status"] = "complete"
    store.put_session(session)

    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "minGroupSize": 3, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 429


# --- Run ---

def test_run_session_202():
    sid = _create_session()
    resp = client.post(f"/api/v1/sessions/{sid}/run", headers=HEADERS)
    assert resp.status_code == 202
    assert resp.json()["status"] == "running"


def test_run_nonexistent_session_404():
    resp = client.post("/api/v1/sessions/does-not-exist/run", headers=HEADERS)
    assert resp.status_code == 404


def test_run_non_pending_session_409():
    sid = _create_session()
    client.post(f"/api/v1/sessions/{sid}/run", headers=HEADERS)
    resp = client.post(f"/api/v1/sessions/{sid}/run", headers=HEADERS)
    assert resp.status_code == 409


# --- List + Get ---

def test_list_sessions():
    resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    assert "sessions" in resp.json()


def test_list_sessions_status_filter():
    sid = _create_session()
    resp = client.get("/api/v1/sessions?status=pending")
    sids = [s["id"] for s in resp.json()["sessions"]]
    assert sid in sids


def test_get_session_200():
    sid = _create_session()
    resp = client.get(f"/api/v1/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sid


def test_get_session_404():
    resp = client.get("/api/v1/sessions/does-not-exist")
    assert resp.status_code == 404


# --- Patch session ---

def test_patch_session_complete_to_saved():
    from data import store
    sid = _create_session()
    # Force complete status directly
    session = store.get_session(sid)
    session["status"] = "complete"
    store.put_session(session)
    resp = client.patch(f"/api/v1/sessions/{sid}", json={"status": "saved"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"


def test_patch_session_running_to_saved_409():
    from data import store
    sid = _create_session()
    session = store.get_session(sid)
    session["status"] = "running"
    store.put_session(session)
    resp = client.patch(f"/api/v1/sessions/{sid}", json={"status": "saved"})
    assert resp.status_code == 409


def test_patch_session_pending_to_cancelled_cleans_up_roles():
    from data import store

    sid = _create_session()
    role = _seed_role(sid)

    resp = client.patch(f"/api/v1/sessions/{sid}", json={"status": "cancelled"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["cleanupStatus"] == "complete"
    assert store.get_role(role["id"]) is None


def test_patch_session_running_to_cancelling():
    from data import store

    sid = _create_session()
    session = store.get_session(sid)
    session["status"] = "running"
    store.put_session(session)

    resp = client.patch(f"/api/v1/sessions/{sid}", json={"status": "cancelled"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelling"


def test_cancelled_session_frees_active_capacity(monkeypatch):
    import config

    monkeypatch.setattr(config, "MAX_ACTIVE_SESSIONS", 1)
    sid = _create_session()
    client.patch(f"/api/v1/sessions/{sid}", json={"status": "cancelled"})

    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": FILTER, "minGroupSize": 3, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 201


def test_clone_complete_session_reuses_launch_config_without_results():
    from data import store

    sid = _create_session()
    session = store.get_session(sid)
    session["status"] = "complete"
    session["layer1RoleIds"] = ["role-1"]
    session["candidateRoleIds"] = ["role-2"]
    store.put_session(session)

    resp = client.post(f"/api/v1/sessions/{sid}/clone", headers=HEADERS)
    assert resp.status_code == 201

    cloned = client.get(f"/api/v1/sessions/{resp.json()['sessionId']}").json()
    assert cloned["status"] == "pending"
    assert cloned["clonedFromSessionId"] == sid
    assert cloned["launchConfig"] == session["launchConfig"]
    assert "layer1RoleIds" not in cloned
    assert "candidateRoleIds" not in cloned


# --- Role endpoints ---

def test_list_roles_failed_session_guarded():
    from data import store
    sid = _create_session()
    session = store.get_session(sid)
    session["status"] = "failed"
    store.put_session(session)
    resp = client.get(f"/api/v1/sessions/{sid}/roles")
    assert resp.status_code == 200
    assert resp.json()["guarded"] is True


def test_list_roles_invalid_role_type_400():
    sid = _create_session()
    resp = client.get(f"/api/v1/sessions/{sid}/roles?roleType=invalid")
    assert resp.status_code == 400


def test_get_role_404():
    resp = client.get("/api/v1/roles/does-not-exist")
    assert resp.status_code == 404


def test_patch_role_rename():
    from data import store
    import uuid
    role = _seed_role("test-session-patch")
    resp = client.patch(f"/api/v1/roles/{role['id']}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_patch_role_valid_status_transition():
    role = _seed_role("test-session-transition")
    resp = client.patch(f"/api/v1/roles/{role['id']}", json={"status": "draft"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


def test_patch_role_invalid_transition_409():
    role = _seed_role("test-session-invalid")
    resp = client.patch(f"/api/v1/roles/{role['id']}", json={"status": "reviewed"})
    assert resp.status_code == 409


def test_patch_role_entitlement_removal():
    role = _seed_role("test-session-ent-removal")
    resp = client.patch(
        f"/api/v1/roles/{role['id']}",
        json={"entitlements": ["e_github"]}
    )
    assert resp.status_code == 200
    remaining = resp.json()["entitlements"].split()
    assert remaining == ["e_github"]


def test_patch_role_merge():
    from data import store
    import uuid
    sid = "test-session-merge"
    target = _seed_role(sid, ent_ids=["e_github", "e_jira"])
    source = _seed_role(sid, ent_ids=["e_confluence", "e_jira"])
    resp = client.patch(
        f"/api/v1/roles/{target['id']}",
        json={"mergeRoleIds": [source["id"]]}
    )
    assert resp.status_code == 200
    merged_ents = set(resp.json()["entitlements"].split())
    assert {"e_github", "e_jira", "e_confluence"}.issubset(merged_ents)
    # Source should be discarded
    source_updated = store.get_role(source["id"])
    assert source_updated["status"] == "discarded"


# --- End-to-end pipeline ---

def test_e2e_full_pipeline():
    """Create session, run it, wait for completion, verify roles exist."""
    sid = _create_session()
    run_resp = client.post(f"/api/v1/sessions/{sid}/run", headers=HEADERS)
    assert run_resp.status_code == 202

    # Poll until terminal — pipeline runs in background thread
    for _ in range(30):
        status = client.get(f"/api/v1/sessions/{sid}").json()["status"]
        if status in ("complete", "failed"):
            break
        time.sleep(0.2)

    session = client.get(f"/api/v1/sessions/{sid}").json()
    assert session["status"] == "complete", f"Pipeline failed: {session.get('errorDetail')}"
    print("totalEntitlementsConsidered:", session.get("totalEntitlementsConsidered"))
    print("totalEntitlementsDropped:", session.get("totalEntitlementsDropped"))
    print("layer1RoleCount:", session.get("layer1RoleCount"))
    print("populationSize:", session.get("populationSize"))
    assert session["layer1RoleCount"] >= 1
    assert "graphMetrics" in session

    roles_resp = client.get(f"/api/v1/sessions/{sid}/roles")
    assert roles_resp.status_code == 200
    roles = roles_resp.json()["roles"]
    assert any(r["roleType"] == "layer1_universal" for r in roles)


def test_e2e_zero_population_fails():
    sid = _create_session(filter_criteria={"JobCode": "NONEXISTENT"})
    client.post(f"/api/v1/sessions/{sid}/run", headers=HEADERS)
    for _ in range(20):
        status = client.get(f"/api/v1/sessions/{sid}").json()["status"]
        if status in ("complete", "failed"):
            break
        time.sleep(0.2)
    session = client.get(f"/api/v1/sessions/{sid}").json()
    assert session["status"] == "failed"
    assert "0 users" in session["errorDetail"]


# --- Helpers ---

def _create_session(filter_criteria=None):
    resp = client.post(
        "/api/v1/sessions",
        json={"filterCriteria": filter_criteria or FILTER, "minGroupSize": 3, "roleType": "job_roles"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["sessionId"]

def test_e2e_birthright_pipeline():
    sid = _create_session_with({"filterCriteria": FILTER, "minGroupSize": 3, "roleType": "birthright"})
    client.post(f"/api/v1/sessions/{sid}/run", headers=HEADERS)
    for _ in range(30):
        status = client.get(f"/api/v1/sessions/{sid}").json()["status"]
        if status in ("complete", "failed"):
            break
        time.sleep(0.2)
    session = client.get(f"/api/v1/sessions/{sid}").json()
    assert session["status"] == "complete"
    assert session["layer1RoleCount"] >= 1
    assert "candidateRoleCount" not in session
    assert "candidateRoleIds" not in session


def _create_session_with(body: dict) -> str:
    resp = client.post("/api/v1/sessions", json=body, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()["sessionId"]

def _seed_role(session_id: str, ent_ids: list[str] = None) -> dict:
    from data import store
    import uuid
    ent_ids = ent_ids or ["e_github", "e_jira", "e_confluence"]
    role = {
        "id": str(uuid.uuid4()),
        "status": "candidate",
        "roleType": "layer2_candidate",

        "sessionId": session_id,
        "name": "Test Role",
        "memberCount": 5,
        "confidence": 0.75,
        "entitlementCount": len(ent_ids),
        "entitlements": " ".join(ent_ids),
        "entitlementMetadata": [
            {"entId": e, "displayName": e, "appId": "", "appName": "",
             "entitlementType": "", "criticality": "", "prevalenceInRole": 0.9,
             "tier": "role_defining"}
            for e in ent_ids
        ],
        "applications": [{"appName": "DevApp", "appId": "", "entitlementCount": len(ent_ids),
                          "pctOfRole": 1.0}],
        "justificationMetadata": {
            "sessionId": session_id, "layer": "layer2", "populationSize": 10,
            "filterDescription": "test", "filterCriteria": {},
            "thresholds": {}, "communityId": 0, "communityModularity": 0.5,
            "cohesionInterpretation": "High", "outliers": [],
        },
    }
    store.put_role(role)
    return role

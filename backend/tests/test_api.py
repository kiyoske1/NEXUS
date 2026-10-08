import os
import tempfile

from fastapi.testclient import TestClient

DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["NEXUS_SERVER_DB"] = DB_FILE

from backend.app.main import app

client = TestClient(app)


def teardown_module():
    try:
        os.remove(DB_FILE)
    except FileNotFoundError:
        pass


def test_api_v1_contract_and_legacy_compatibility():
    response = client.get("/api/v1")
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"

    docs = client.get("/api/v1/openapi.json")
    assert docs.status_code == 200
    assert docs.json()["info"]["version"] == "1.0.0"
    assert "/api/v1/auth/login" in docs.json()["paths"]

    legacy = client.get("/health")
    assert legacy.status_code == 200
    assert legacy.headers["X-NEXUS-API-Version"] == "1.0.0"
    assert legacy.headers["Deprecation"] == "true"


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "1.0.0"


def test_auth_and_sync_flow():
    response = client.post("/auth/register", json={
        "name": "Vova", "email": "vova@example.com",
        "username": "vova", "password": "secret123",
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    refresh_token = response.json()["refresh_token"]
    device_id = response.json()["device_id"]
    headers = {"Authorization": f"Bearer {token}"}

    devices = client.get("/devices", headers=headers)
    assert devices.status_code == 200
    assert devices.json()[0]["id"] == device_id

    refreshed = client.post("/auth/refresh", json={
        "refresh_token": refresh_token, "device_id": device_id,
    })
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != token
    assert refreshed.json()["refresh_token"] != refresh_token
    stale_refresh = client.post("/auth/refresh", json={
        "refresh_token": refresh_token, "device_id": device_id,
    })
    assert stale_refresh.status_code == 401
    headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}

    assert client.get("/me", headers=headers).json()["username"] == "vova"

    duplicate = client.post("/auth/register", json={
        "name": "Other", "email": "VOVA@example.com",
        "username": "other", "password": "secret123",
    })
    assert duplicate.status_code == 409

    login = client.post("/auth/login", json={
        "username_or_email": "vova", "password": "secret123",
    })
    assert login.status_code == 200
    login_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    bad_login = client.post("/auth/login", json={
        "username_or_email": "vova", "password": "wrong",
    })
    assert bad_login.status_code == 401

    push = client.post("/sync/push", headers=login_headers, json={"records": [
        {"entity": "task", "client_id": "task-1",
         "payload": {"title": "Ship NEXUS", "done": False}},
        {"entity": "finance", "client_id": "tx-1",
         "payload": {"amount": 100, "kind": "income"}},
    ]})
    assert push.status_code == 200
    assert push.json()["accepted"] == 2

    pull = client.get("/sync/pull", headers=login_headers)
    assert pull.status_code == 200
    assert {r["client_id"] for r in pull.json()["records"]} == {"task-1", "tx-1"}

    logout = client.post("/auth/logout", headers=login_headers)
    assert logout.status_code == 200
    assert client.get("/me", headers=login_headers).status_code == 401


def test_sync_is_last_write_wins():
    response = client.post("/auth/register", json={
        "name": "Sync", "email": "sync@example.com",
        "username": "sync", "password": "secret123",
    })
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    newer = {"entity": "task", "client_id": "1",
             "payload": {"title": "new"}, "updated_at": "2026-01-02T00:00:00+00:00"}
    older = {"entity": "task", "client_id": "1",
             "payload": {"title": "old"}, "updated_at": "2026-01-01T00:00:00+00:00"}

    assert client.post("/sync/push", headers=headers, json={"records": [newer]}).json()["accepted"] == 1
    assert client.post("/sync/push", headers=headers, json={"records": [older]}).json()["accepted"] == 0
    records = client.get("/sync/pull", headers=headers).json()["records"]
    assert records[0]["payload"]["title"] == "new"


def test_logout_only_revokes_current_device_and_logout_all_revokes_everything():
    first = client.post("/auth/register", json={
        "name": "Devices", "email": "devices@example.com",
        "username": "devices", "password": "secret123",
        "device_id": "device-a", "device_name": "Desktop",
    }).json()
    second = client.post("/auth/login", json={
        "username_or_email": "devices", "password": "secret123",
        "device_id": "device-b", "device_name": "Phone",
    }).json()

    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    assert client.get("/me", headers=first_headers).status_code == 200
    assert client.get("/me", headers=second_headers).status_code == 200

    assert client.post("/auth/logout", headers=first_headers).status_code == 200
    assert client.get("/me", headers=first_headers).status_code == 401
    assert client.get("/me", headers=second_headers).status_code == 200

    assert client.post("/auth/logout-all", headers=second_headers).status_code == 200
    assert client.get("/me", headers=second_headers).status_code == 401
    assert client.post("/auth/refresh", json={
        "refresh_token": second["refresh_token"], "device_id": "device-b"
    }).status_code == 401

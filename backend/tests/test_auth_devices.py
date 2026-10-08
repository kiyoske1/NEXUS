import os
import tempfile

DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["NEXUS_SERVER_DB"] = DB_FILE

from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_refresh_rotation_and_device_revoke():
    registered = client.post("/auth/register", json={
        "name": "Device", "email": "device-test@example.com",
        "username": "device-test", "password": "secret123",
        "device_name": "Test desktop",
    })
    assert registered.status_code == 201
    data = registered.json()
    access = data["access_token"]
    refresh = data["refresh_token"]
    device_id = data["device_id"]
    headers = {"Authorization": f"Bearer {access}"}

    devices = client.get("/devices", headers=headers)
    assert devices.status_code == 200
    assert devices.json()[0]["id"] == device_id

    rotated = client.post("/auth/refresh", json={
        "refresh_token": refresh, "device_id": device_id,
    })
    assert rotated.status_code == 200
    assert rotated.json()["access_token"] != access
    assert rotated.json()["refresh_token"] != refresh

    reused = client.post("/auth/refresh", json={
        "refresh_token": refresh, "device_id": device_id,
    })
    assert reused.status_code == 401

    revoke = client.delete(f"/devices/{device_id}", headers=headers)
    assert revoke.status_code == 200

    after_revoke = client.get("/devices", headers=headers)
    assert after_revoke.status_code == 200
    assert all(item["id"] != device_id for item in after_revoke.json())


def teardown_module():
    try:
        os.remove(DB_FILE)
    except FileNotFoundError:
        pass

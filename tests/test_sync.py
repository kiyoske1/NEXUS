from nexus.database import Database
from nexus.sync import SyncClient


def test_sync_pushes_new_and_changed_records_only(tmp_path):
    db = Database(tmp_path / "sync.db")
    task_id = db.add_task("Cloud quest", xp=50)
    client = SyncClient(db, api_url="http://example.test", token="token")

    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return {"server_time": "2026-10-08T00:00:00+00:00", "records": []}
        return {"accepted": len(payload["records"]), "server_time": "2026-10-08T00:00:00+00:00"}

    client._request = fake_request

    first = client.sync()
    assert first["pushed"] == 1
    assert calls[-1][1] == "/sync/push"

    second = client.sync()
    assert second["pushed"] == 0

    db.update_task(task_id, "Cloud quest edited", "Work", 80)
    third = client.sync()
    assert third["pushed"] == 1
    assert calls[-1][2]["records"][0]["payload"]["title"] == "Cloud quest edited"

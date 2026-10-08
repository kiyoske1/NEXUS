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


def test_sync_history_records_success_and_errors(tmp_path):
    db = Database(tmp_path / "history.db")
    db.add_task("History quest", xp=10)
    client = SyncClient(db, api_url="http://example.test", token="token")

    def fake_request(method, path, payload=None):
        if method == "GET":
            return {"server_time": "2026-10-08T01:00:00+00:00", "records": []}
        return {"accepted": len(payload["records"]), "server_time": "2026-10-08T01:00:00+00:00"}

    client._request = fake_request
    client.sync()
    history = client.list_history()
    assert history[0]["status"] == "success"
    assert history[0]["pushed"] == 1
    assert history[0]["pulled"] == 0

    def failing_request(method, path, payload=None):
        raise RuntimeError("boom")

    client._request = failing_request
    try:
        client.sync()
    except RuntimeError:
        pass
    else:
        raise AssertionError("sync should fail")

    history = client.list_history()
    assert history[0]["status"] == "error"
    assert "boom" in history[0]["error"]
    assert len(history) == 2


def test_remote_sync_ignores_unknown_payload_columns(tmp_path):
    db = Database(tmp_path / "remote-fields.db")
    client = SyncClient(db, api_url="http://example.test", token="token")
    client._upsert_remote("tasks", "remote-task-1", {
        "title": "Remote quest",
        "category": "Learning",
        "xp": 30,
        "created_at": "2026-10-09T00:00:00",
        "not_a_real_column; DROP TABLE tasks; --": "ignored",
    })
    assert db.get_tasks()[0]["title"] == "Remote quest"
    assert db.get_tasks()[0]["xp"] == 30

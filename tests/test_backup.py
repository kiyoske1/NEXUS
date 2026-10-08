import json
import sqlite3
import zipfile

from nexus.backup import create_backup, create_full_backup, export_json
from nexus.database import Database


def test_backup_is_a_readable_database(tmp_path):
    db = Database(tmp_path / "source.db")
    db.add_task("Keep building", xp=40)
    destination = create_backup(db, tmp_path / "backups" / "nexus-backup.db")
    with sqlite3.connect(destination) as connection:
        row = connection.execute("SELECT title, xp FROM tasks").fetchone()
    assert row == ("Keep building", 40)


def test_json_export_contains_all_data_tables(tmp_path):
    db = Database(tmp_path / "source.db")
    db.add_transaction("First client", 250, "income")
    destination = export_json(db, tmp_path / "export.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["app"] == "NEXUS"
    assert payload["data"]["transactions"][0]["title"] == "First client"
    assert "journal_entries" in payload["data"]


def test_backup_cannot_overwrite_live_database(tmp_path):
    db = Database(tmp_path / "source.db")
    db.add_task("Do not lose this")
    try:
        create_backup(db, db.path)
    except ValueError as error:
        assert "different from the live database" in str(error)
    else:
        raise AssertionError("Expected backup destination guard")


def test_full_backup_contains_account_registry_and_workspaces(tmp_path):
    db = Database(tmp_path / "source.db")
    db.create_account("Alice", "alice@example.com", "alice", "secret1")
    db.add_task("Alice quest", xp=30)
    db.create_account("Bob", "bob@example.com", "bob", "secret2")
    db.add_task("Bob quest", xp=50)

    destination = create_full_backup(db, tmp_path / "nexus-backup.nexus.zip")
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "accounts/nexus_accounts.db" in names
        assert "accounts/workspaces/account_1.db" in names
        assert "accounts/workspaces/account_2.db" in names

import sqlite3
from datetime import date

import pytest

from nexus.database import Database
from nexus.sync import SyncClient


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test-nexus.db")


def test_task_can_be_created_and_completed(db):
    task_id = db.add_task("Ship first version", "Learning", 50)
    assert db.get_tasks()[0]["id"] == task_id
    assert db.get_tasks()[0]["done"] == 0
    assert db.complete_task(task_id) is True
    assert db.complete_task(task_id) is False
    stats = db.stats()
    assert stats["tasks_done"] == 1
    assert stats["xp"] == 50


def test_empty_task_is_rejected(db):
    with pytest.raises(ValueError):
        db.add_task("   ")


def test_habit_checkin_can_be_toggled(db):
    habit_id = db.add_habit("Read")
    day = date(2026, 1, 2).isoformat()
    assert db.get_habits(day)[0]["done"] == 0
    assert db.toggle_habit(habit_id, day) is True
    assert db.get_habits(day)[0]["done"] == 1
    assert db.toggle_habit(habit_id, day) is False
    assert db.get_habits(day)[0]["done"] == 0


def test_transactions_update_balance(db):
    db.add_transaction("Freelance", 100, "income")
    db.add_transaction("Lunch", 15.5, "expense")
    assert db.stats()["balance"] == 84.5


def test_invalid_transactions_are_rejected(db):
    with pytest.raises(ValueError):
        db.add_transaction("Coffee", -1, "expense")
    with pytest.raises(ValueError):
        db.add_transaction("Coffee", 1, "refund")


def test_journal_and_focus_are_persisted(db):
    db.add_journal_entry("Today", "Started building NEXUS")
    db.add_focus_session(25)
    assert db.get_journal_entries()[0]["body"] == "Started building NEXUS"
    assert db.stats()["focus_minutes"] == 25


def test_weekly_activity_includes_focus_minutes_for_today(db):
    db.add_focus_session(25)
    today = date.today().isoformat()
    activity = db.weekly_activity()
    assert len(activity) == 7
    today_row = next(day for day in activity if day["date"] == today)
    assert today_row["focus"] == 25


def test_habit_streak_counts_consecutive_days(db):
    habit_id = db.add_habit("Walk")
    end = date(2026, 1, 5)
    for day in (date(2026, 1, 3), date(2026, 1, 4), end):
        db.toggle_habit(habit_id, day.isoformat())
    assert db.habit_streak(habit_id, end) == 3


def test_habit_streak_survives_until_today_is_missed(db):
    habit_id = db.add_habit("Stretch")
    yesterday = date(2026, 2, 10)
    db.toggle_habit(habit_id, yesterday.isoformat())
    assert db.habit_streak(habit_id, date(2026, 2, 11)) == 1
    assert db.habit_streak(habit_id, date(2026, 2, 12)) == 0


def test_journal_entry_can_be_deleted(db):
    entry_id = db.add_journal_entry("Temporary thought", "This should disappear.")
    assert any(entry["id"] == entry_id for entry in db.get_journal_entries())
    db.delete_journal_entry(entry_id)
    assert all(entry["id"] != entry_id for entry in db.get_journal_entries())


def test_records_can_be_edited(db):
    task = db.add_task("Old task", "Work", 20)
    db.update_task(task, "New task", "Learning", 50)
    assert db.get_tasks()[0]["title"] == "New task"
    habit = db.add_habit("Old habit")
    db.update_habit(habit, "New habit")
    assert db.get_habits()[0]["title"] == "New habit"
    tx = db.add_transaction("Old", 10, "expense")
    db.update_transaction(tx, "New", 25, "income")
    assert db.get_transactions()[0]["amount"] == 25
    entry = db.add_journal_entry("Old", "Text")
    db.update_journal_entry(entry, "New", "Updated")
    assert db.get_journal_entries()[0]["body"] == "Updated"


def test_profile_is_saved_and_password_is_verified(db):
    db.save_profile("Vova", "vova@example.com", "vova", "secret")
    assert db.get_profile()["username"] == "vova"
    assert db.verify_profile_password("secret") is True
    assert db.verify_profile_password("wrong") is False


def test_legacy_profile_schema_is_migrated(tmp_path):
    path = tmp_path / "legacy-nexus.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE profile (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            "INSERT INTO profile(id, name, email, username) VALUES (1, 'Vova', 'vova@example.com', 'vova')"
        )
        connection.commit()

    migrated = Database(path)
    profile = migrated.get_profile()

    assert profile["username"] == "vova"
    assert profile["password_hash"] == ""
    assert profile["created_at"] == ""

    migrated.save_profile("Vova", "vova@example.com", "vova", "secret")
    assert migrated.verify_profile_password("secret") is True


def test_multiple_accounts_have_isolated_workspaces(tmp_path):
    db = Database(tmp_path / "multi.db")
    db.create_account("Alice", "alice@example.com", "alice", "secret1")
    db.add_task("Alice private quest")

    db.create_account("Bob", "bob@example.com", "bob", "secret2")
    assert db.get_tasks() == []
    assert len(db.list_accounts()) == 2

    assert db.authenticate_account("alice", "wrong") is False
    assert db.authenticate_account("alice@example.com", "secret1") is True
    assert [task["title"] for task in db.get_tasks()] == ["Alice private quest"]

    assert db.authenticate_account("bob", "secret2") is True
    assert db.get_tasks() == []


def test_profile_edit_cannot_take_another_account_identity(tmp_path):
    db = Database(tmp_path / "profiles.db")
    db.create_account("Alice", "alice@example.com", "alice", "secret1")
    db.create_account("Bob", "bob@example.com", "bob", "secret2")
    assert db.authenticate_account("alice", "secret1") is True

    with pytest.raises(ValueError):
        db.save_profile("Alice", "bob@example.com", "alice", "")

    assert db.get_profile()["email"] == "alice@example.com"



def test_dashboard_level_and_streak(tmp_path):
    db = Database(tmp_path / "dashboard.db")
    db.save_profile("Vova", "vova@example.com", "vova", "secret")
    db.add_task("Today quest", xp=500)
    db.complete_task(1)
    assert db.level_info()["level"] == 2
    assert db.streak_days() == 1
    summary = db.dashboard_summary()
    assert summary["done_today"] == 1
    assert summary["week_done"] == 1
    assert summary["xp"] == 500


def test_transaction_can_be_deleted(tmp_path):
    db = Database(tmp_path / "delete-transaction.db")
    transaction_id = db.add_transaction("Temporary expense", 25, "expense")
    assert len(db.get_transactions()) == 1
    db.delete_transaction(transaction_id)
    assert db.get_transactions() == []

def test_sync_device_identity_isolated_per_workspace(tmp_path):
    first = Database(tmp_path / "first.db")
    second = Database(tmp_path / "second.db")
    first_sync = SyncClient(first)
    second_sync = SyncClient(second)
    assert first_sync.device_id != second_sync.device_id
    assert (tmp_path / "first.db.device_id").exists()
    assert (tmp_path / "second.db.device_id").exists()


def test_sync_device_identity_is_stable(tmp_path):
    path = tmp_path / "stable.db"
    first = SyncClient(Database(path))
    second = SyncClient(Database(path))
    assert first.device_id == second.device_id

def test_create_records_does_not_deadlock(tmp_path):
    db = Database(tmp_path / "records.db")
    task_id = db.add_task("Ship quest")
    habit_id = db.add_habit("Read")
    transaction_id = db.add_transaction("Salary", 100, "income")
    assert any(row["id"] == task_id for row in db.get_tasks())
    assert any(row["id"] == habit_id for row in db.get_habits())
    assert any(row["id"] == transaction_id for row in db.get_transactions())
    assert db.unread_notification_count() >= 2

def test_focus_sessions_can_be_loaded_by_day(db):
    db.add_focus_session(25)
    today = date.today().isoformat()
    sessions = db.get_focus_sessions(today)
    assert len(sessions) == 1
    assert sessions[0]["duration_minutes"] == 25
    assert db.get_focus_sessions("1999-01-01") == []


def test_transactions_reject_non_finite_amounts(db):
    for amount in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            db.add_transaction("Invalid amount", amount, "expense")


def test_database_connection_uses_busy_timeout(db):
    with db.connect() as connection:
        timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout >= 5000


def test_transaction_updates_reject_non_finite_amounts(db):
    transaction_id = db.add_transaction("Valid amount", 10, "expense")
    for amount in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            db.update_transaction(transaction_id, "Invalid amount", amount, "expense")
    assert db.get_transactions()[0]["amount"] == 10

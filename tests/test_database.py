from datetime import date

import pytest

from nexus.database import Database


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

"""Local persistence for NEXUS.

All user data stays on the machine. The database is created lazily in ~/.nexus.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path.home() / ".nexus" / "nexus.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Personal',
                    xp INTEGER NOT NULL DEFAULT 25,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS habit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                    log_date TEXT NOT NULL,
                    UNIQUE(habit_id, log_date)
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    amount REAL NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS focus_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    duration_minutes INTEGER NOT NULL,
                    completed_at TEXT NOT NULL
                );
            """)

    @staticmethod
    def now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def add_task(self, title: str, category: str = "Personal", xp: int = 25) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO tasks(title, category, xp, created_at) VALUES (?, ?, ?, ?)",
                (title, category.strip() or "Personal", max(1, int(xp)), self.now()),
            )
            return int(cursor.lastrowid)

    def get_tasks(self, include_done: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM tasks"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY done ASC, id DESC"
        with self.connect() as db:
            return [dict(row) for row in db.execute(query).fetchall()]

    def complete_task(self, task_id: int) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE tasks SET done = 1, completed_at = ? WHERE id = ? AND done = 0",
                (self.now(), task_id),
            )
            return cursor.rowcount == 1

    def delete_task(self, task_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def add_habit(self, title: str) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Habit title cannot be empty")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO habits(title, created_at) VALUES (?, ?)",
                (title, self.now()),
            )
            return int(cursor.lastrowid)

    def get_habits(self, on_date: str | None = None) -> list[dict[str, Any]]:
        day = on_date or date.today().isoformat()
        with self.connect() as db:
            rows = db.execute("""
                SELECT h.id, h.title, h.created_at,
                       CASE WHEN l.id IS NULL THEN 0 ELSE 1 END AS done
                FROM habits h
                LEFT JOIN habit_logs l ON l.habit_id = h.id AND l.log_date = ?
                ORDER BY h.id DESC
            """, (day,)).fetchall()
            return [dict(row) for row in rows]

    def toggle_habit(self, habit_id: int, on_date: str | None = None) -> bool:
        day = on_date or date.today().isoformat()
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?",
                (habit_id, day),
            ).fetchone()
            if existing:
                db.execute("DELETE FROM habit_logs WHERE id = ?", (existing["id"],))
                return False
            db.execute(
                "INSERT INTO habit_logs(habit_id, log_date) VALUES (?, ?)",
                (habit_id, day),
            )
            return True

    def delete_habit(self, habit_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))

    def add_transaction(self, title: str, amount: float, kind: str) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Transaction title cannot be empty")
        if kind not in {"income", "expense"}:
            raise ValueError("Transaction kind must be income or expense")
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO transactions(title, amount, kind, created_at) VALUES (?, ?, ?, ?)",
                (title, round(amount, 2), kind, self.now()),
            )
            return int(cursor.lastrowid)

    def get_transactions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM transactions ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_journal_entry(self, title: str, body: str) -> int:
        title, body = title.strip(), body.strip()
        if not title and not body:
            raise ValueError("Journal entry cannot be empty")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO journal_entries(title, body, created_at) VALUES (?, ?, ?)",
                (title or "Untitled", body, self.now()),
            )
            return int(cursor.lastrowid)

    def get_journal_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM journal_entries ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_focus_session(self, duration_minutes: int) -> None:
        if duration_minutes < 1:
            raise ValueError("Duration must be positive")
        with self.connect() as db:
            db.execute(
                "INSERT INTO focus_sessions(duration_minutes, completed_at) VALUES (?, ?)",
                (int(duration_minutes), self.now()),
            )

    def stats(self) -> dict[str, Any]:
        today = date.today().isoformat()
        with self.connect() as db:
            task = db.execute("""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END), 0) AS done,
                       COALESCE(SUM(CASE WHEN done = 1 THEN xp ELSE 0 END), 0) AS xp
                FROM tasks
            """).fetchone()
            habits = db.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN l.id IS NOT NULL THEN 1 ELSE 0 END) AS done
                FROM habits h
                LEFT JOIN habit_logs l ON l.habit_id = h.id AND l.log_date = ?
            """, (today,)).fetchone()
            money = db.execute("""
                SELECT COALESCE(SUM(CASE WHEN kind = 'income' THEN amount ELSE -amount END), 0) AS balance
                FROM transactions
            """).fetchone()
            focus = db.execute("""
                SELECT COALESCE(SUM(duration_minutes), 0) AS minutes
                FROM focus_sessions
            """).fetchone()
        return {
            "tasks_total": task["total"],
            "tasks_done": task["done"],
            "xp": task["xp"],
            "habits_total": habits["total"],
            "habits_done": habits["done"] or 0,
            "balance": round(money["balance"], 2),
            "focus_minutes": focus["minutes"],
        }

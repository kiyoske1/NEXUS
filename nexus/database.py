"""Local persistence for NEXUS.

All user data stays on the machine. The database is created lazily in ~/.nexus.
"""
from __future__ import annotations

import sqlite3
import hashlib
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self._explicit_path = path is not None
        self.path = Path(path) if path else Path.home() / ".nexus" / "nexus.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._accounts_dir = self.path.parent / f"{self.path.stem}_accounts"
        self._accounts_index = self.path.parent / f"{self.path.stem}_accounts.db"
        self._accounts_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._initialize_account_registry()

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
                CREATE TABLE IF NOT EXISTS profile (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL DEFAULT '',
                    salt TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS focus_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    duration_minutes INTEGER NOT NULL,
                    completed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    level TEXT NOT NULL DEFAULT 'info',
                    read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
            """)
            self._migrate_profile_schema(db)

    @staticmethod
    def _migrate_profile_schema(db: sqlite3.Connection) -> None:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(profile)").fetchall()}
        required = {
            "password_hash": "TEXT NOT NULL DEFAULT ''",
            "salt": "TEXT NOT NULL DEFAULT ''",
            "created_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in required.items():
            if name not in columns:
                db.execute(f"ALTER TABLE profile ADD COLUMN {name} {definition}")

    def _connect_accounts(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._accounts_index)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_account_registry(self) -> None:
        with self._connect_accounts() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    db_path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
            """)
            profile = self.get_profile()
            if profile and profile.get("password_hash"):
                existing = db.execute(
                    "SELECT id FROM accounts WHERE db_path = ? OR username = ? OR email = ?",
                    (str(self.path), profile["username"], profile["email"]),
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT INTO accounts(name, email, username, db_path, created_at) VALUES (?, ?, ?, ?, ?)",
                        (profile["name"], profile["email"], profile["username"], str(self.path), profile.get("created_at") or self.now()),
                    )

    def dashboard_summary(self) -> dict[str, Any]:
        today = date.today().isoformat()
        with self.connect() as db:
            open_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE done = 0").fetchone()[0]
            done_today = db.execute("SELECT COUNT(*) FROM tasks WHERE done = 1 AND DATE(completed_at) = ?", (today,)).fetchone()[0]
            focus_today = db.execute("SELECT COALESCE(SUM(duration_minutes), 0) FROM focus_sessions WHERE DATE(completed_at) = ?", (today,)).fetchone()[0]
            habit_done_today = db.execute("SELECT COUNT(*) FROM habit_logs WHERE log_date = ?", (today,)).fetchone()[0]
            balance = db.execute("""
                SELECT COALESCE(SUM(CASE WHEN kind = 'income' THEN amount ELSE -amount END), 0)
                FROM transactions
            """).fetchone()[0]
            weekly = db.execute("""
                SELECT DATE(completed_at) AS day, COUNT(*) AS count
                FROM tasks
                WHERE done = 1 AND DATE(completed_at) >= DATE(?, '-6 days')
                GROUP BY DATE(completed_at)
            """, (today,)).fetchall()
        weekly_map = {row["day"]: row["count"] for row in weekly}
        week_done = sum(weekly_map.values())
        return {
            "open_tasks": open_tasks,
            "done_today": done_today,
            "focus_today": focus_today,
            "habit_done_today": habit_done_today,
            "balance": balance,
            "week_done": week_done,
            "week_days": [weekly_map.get((date.today()).fromordinal(date.today().toordinal() - offset).isoformat(), 0) for offset in range(6, -1, -1)],
        }

    def account_summary(self) -> dict[str, Any]:
        profile = self.get_profile() or {}
        stats = self.stats()
        with self.connect() as db:
            first = db.execute("SELECT MIN(created_at) FROM tasks").fetchone()[0]
            last = db.execute("SELECT MAX(created_at) FROM journal_entries").fetchone()[0]
            focus_count = db.execute("SELECT COUNT(*) FROM focus_sessions").fetchone()[0]
        return {
            "name": profile.get("name", ""),
            "email": profile.get("email", ""),
            "username": profile.get("username", ""),
            "created_at": profile.get("created_at", ""),
            "tasks": stats["tasks_total"],
            "tasks_done": stats["tasks_done"],
            "xp": stats["xp"],
            "focus_sessions": focus_count,
            "first_task": first,
            "last_journal": last,
        }

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect_accounts() as db:
            rows = db.execute("SELECT id, name, email, username, db_path, created_at FROM accounts ORDER BY name COLLATE NOCASE").fetchall()
            return [dict(row) for row in rows]

    def create_account(self, name: str, email: str, username: str, password: str) -> None:
        name, email, username = name.strip(), email.strip().lower(), username.strip()
        if not name:
            raise ValueError("Name cannot be empty")
        if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email")
        if not username:
            raise ValueError("Username cannot be empty")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        with self._connect_accounts() as accounts:
            if accounts.execute("SELECT 1 FROM accounts WHERE email = ? COLLATE NOCASE", (email,)).fetchone():
                raise ValueError("That email is already registered on this PC.")
            if accounts.execute("SELECT 1 FROM accounts WHERE username = ? COLLATE NOCASE", (username,)).fetchone():
                raise ValueError("That username is already registered on this PC.")
            account_id = int(accounts.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM accounts").fetchone()["next_id"])
            db_path = self._accounts_dir / f"account_{account_id}.db"

        old_path = self.path
        self.path = db_path
        try:
            self._initialize()
            self.save_profile(name, email, username, password, _register=False)
            with self._connect_accounts() as accounts:
                accounts.execute(
                    "INSERT INTO accounts(id, name, email, username, db_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (account_id, name, email, username, str(db_path), self.now()),
                )
        except Exception:
            self.path = old_path
            if db_path.exists():
                try:
                    db_path.unlink()
                except OSError:
                    pass
            raise

    def authenticate_account(self, identifier: str, password: str) -> bool:
        identifier = identifier.strip()
        with self._connect_accounts() as accounts:
            row = accounts.execute(
                "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE",
                (identifier, identifier.lower()),
            ).fetchone()
        if not row:
            return False
        candidate = Path(row["db_path"])
        if not candidate.exists():
            return False
        old_path = self.path
        self.path = candidate
        try:
            if self.verify_profile_password(password):
                return True
            self.path = old_path
            return False
        except Exception:
            self.path = old_path
            raise

    def switch_to_account(self, account_id: int) -> bool:
        with self._connect_accounts() as accounts:
            row = accounts.execute("SELECT db_path FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
        if not row:
            return False
        candidate = Path(row["db_path"])
        if not candidate.exists():
            return False
        self.path = candidate
        return True

    def delete_account(self, account_id: int, password: str) -> None:
        with self._connect_accounts() as accounts:
            row = accounts.execute("SELECT * FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
        if not row:
            raise ValueError("Account not found.")
        candidate = Path(row["db_path"])
        if not candidate.exists():
            raise ValueError("Account workspace is missing.")
        old_path = self.path
        self.path = candidate
        try:
            if not self.verify_profile_password(password):
                raise ValueError("Incorrect password.")
        finally:
            self.path = old_path
        with self._connect_accounts() as accounts:
            accounts.execute("DELETE FROM accounts WHERE id = ?", (int(account_id),))
        if candidate != old_path and candidate.exists():
            candidate.unlink()

    def current_account(self) -> dict[str, Any] | None:
        return self.get_profile()

    @staticmethod
    def now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def log_activity(self, action: str, detail: str = "") -> int:
        with self.connect() as db:
            cursor = db.execute("INSERT INTO activity_log(action, detail, created_at) VALUES (?, ?, ?)", (action.strip() or "Activity", detail.strip(), self.now()))
            return int(cursor.lastrowid)

    def add_notification(self, title: str, body: str = "", level: str = "info") -> int:
        with self.connect() as db:
            cursor = db.execute("INSERT INTO notifications(title, body, level, created_at) VALUES (?, ?, ?, ?)", (title.strip() or "NEXUS", body.strip(), level, self.now()))
            return int(cursor.lastrowid)

    def get_notifications(self, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE read = 0"
        query += " ORDER BY id DESC LIMIT ?"
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, (max(1, int(limit)),)).fetchall()]

    def unread_notification_count(self) -> int:
        with self.connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM notifications WHERE read = 0").fetchone()[0])

    def mark_notification_read(self, notification_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))

    def mark_all_notifications_read(self) -> None:
        with self.connect() as db:
            db.execute("UPDATE notifications SET read = 1 WHERE read = 0")

    def get_activity(self, limit: int = 80) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)).fetchall()]

    def add_task(self, title: str, category: str = "Personal", xp: int = 25) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO tasks(title, category, xp, created_at) VALUES (?, ?, ?, ?)",
                (title, category.strip() or "Personal", max(1, int(xp)), self.now()),
            )
            task_id = int(cursor.lastrowid)
            self.log_activity("Quest created", title)
            self.add_notification("New quest added", title, "info")
            return task_id

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
            changed = cursor.rowcount == 1
        if changed:
            self.log_activity("Quest completed", f"{task_id}")
            self.add_notification("Quest complete", "XP earned. Keep the momentum going.", "success")
        return changed

    def delete_task(self, task_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def update_task(self, task_id: int, title: str, category: str, xp: int) -> None:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        with self.connect() as db:
            db.execute("UPDATE tasks SET title = ?, category = ?, xp = ? WHERE id = ?", (title, category.strip() or "Personal", max(1, int(xp)), task_id))

    def update_habit(self, habit_id: int, title: str) -> None:
        title = title.strip()
        if not title:
            raise ValueError("Habit title cannot be empty")
        with self.connect() as db:
            db.execute("UPDATE habits SET title = ? WHERE id = ?", (title, habit_id))

    def add_habit(self, title: str) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Habit title cannot be empty")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO habits(title, created_at) VALUES (?, ?)",
                (title, self.now()),
            )
            habit_id = int(cursor.lastrowid)
            self.log_activity("Habit created", title)
            self.add_notification("Habit added", title, "info")
            return habit_id

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
        self.log_activity("Habit checked in", f"{habit_id} · {day}")
        return True

    def delete_habit(self, habit_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))

    def update_transaction(self, transaction_id: int, title: str, amount: float, kind: str) -> None:
        title, amount = title.strip(), float(amount)
        if not title:
            raise ValueError("Transaction title cannot be empty")
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        if kind not in {"income", "expense"}:
            raise ValueError("Transaction kind must be income or expense")
        with self.connect() as db:
            db.execute("UPDATE transactions SET title = ?, amount = ?, kind = ? WHERE id = ?", (title, round(amount, 2), kind, transaction_id))

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
            transaction_id = int(cursor.lastrowid)
            self.log_activity("Finance entry added", title)
            return transaction_id

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
            entry_id = int(cursor.lastrowid)
            self.log_activity("Journal entry created", title or "Untitled")
            return entry_id

    def get_journal_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM journal_entries ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_journal_entry(self, entry_id: int, title: str, body: str) -> None:
        title, body = title.strip(), body.strip()
        if not title and not body:
            raise ValueError("Journal entry cannot be empty")
        with self.connect() as db:
            db.execute("UPDATE journal_entries SET title = ?, body = ? WHERE id = ?", (title or "Untitled", body, entry_id))

    def delete_journal_entry(self, entry_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))

    def get_profile(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT id, name, email, username, password_hash, created_at FROM profile WHERE id = 1").fetchone()
            return dict(row) if row else None

    def save_profile(self, name: str, email: str, username: str, password: str = "", _register: bool = True) -> None:
        name, email, username = name.strip(), email.strip(), username.strip()
        if not name:
            raise ValueError("Name cannot be empty")
        if not email or "@" not in email:
            raise ValueError("Enter a valid email")
        if not username:
            raise ValueError("Username cannot be empty")
        if _register:
            with self._connect_accounts() as accounts:
                current = accounts.execute("SELECT id FROM accounts WHERE db_path = ?", (str(self.path),)).fetchone()
                current_id = current["id"] if current else None
                conflict = accounts.execute(
                    "SELECT id FROM accounts WHERE (email = ? COLLATE NOCASE OR username = ? COLLATE NOCASE) AND id != COALESCE(?, -1)",
                    (email, username, current_id),
                ).fetchone()
                if conflict:
                    raise ValueError("That email or username is already registered on this PC.")
        with self.connect() as db:
            existing = db.execute("SELECT password_hash, salt FROM profile WHERE id = 1").fetchone()
            salt = existing["salt"] if existing and existing["salt"] else secrets.token_hex(16)
            password_hash = existing["password_hash"] if existing else ""
            if password:
                password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
            created_at = existing["created_at"] if existing and existing["created_at"] else self.now()
            db.execute("INSERT INTO profile(id, name, email, username, password_hash, salt, created_at) VALUES (1, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, email=excluded.email, username=excluded.username, password_hash=excluded.password_hash, salt=excluded.salt", (name, email, username, password_hash, salt, created_at))

        if _register:
            with self._connect_accounts() as accounts:
                existing = accounts.execute("SELECT id FROM accounts WHERE db_path = ?", (str(self.path),)).fetchone()
                if existing:
                    accounts.execute("UPDATE accounts SET name = ?, email = ?, username = ? WHERE id = ?", (name, email, username, existing["id"]))
                elif password_hash:
                    try:
                        accounts.execute("INSERT INTO accounts(name, email, username, db_path, created_at) VALUES (?, ?, ?, ?, ?)", (name, email, username, str(self.path), created_at))
                    except sqlite3.IntegrityError as error:
                        raise ValueError("That email or username is already registered on this PC.") from error

    def verify_profile_password(self, password: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT password_hash, salt FROM profile WHERE id = 1").fetchone()
        if not row or not row["password_hash"]:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), row["salt"].encode("utf-8"), 120_000).hex()
        return secrets.compare_digest(digest, row["password_hash"])

    def add_focus_session(self, duration_minutes: int) -> None:
        if duration_minutes < 1:
            raise ValueError("Duration must be positive")
        with self.connect() as db:
            db.execute(
                "INSERT INTO focus_sessions(duration_minutes, completed_at) VALUES (?, ?)",
                (int(duration_minutes), self.now()),
            )
        self.log_activity("Focus session completed", f"{int(duration_minutes)} minutes")
        self.add_notification("Focus session complete", f"{int(duration_minutes)} minutes logged.", "success")

    def weekly_activity(self, end_date: date | None = None) -> list[dict[str, Any]]:
        """Return activity totals for the seven calendar days ending on end_date."""
        from datetime import timedelta

        end = end_date or date.today()
        start = end - timedelta(days=6)
        with self.connect() as db:
            task_rows = db.execute("""
                SELECT substr(completed_at, 1, 10) AS day, COUNT(*) AS total
                FROM tasks
                WHERE done = 1 AND completed_at IS NOT NULL
                  AND substr(completed_at, 1, 10) BETWEEN ? AND ?
                GROUP BY substr(completed_at, 1, 10)
            """, (start.isoformat(), end.isoformat())).fetchall()
            focus_rows = db.execute("""
                SELECT substr(completed_at, 1, 10) AS day,
                       COALESCE(SUM(duration_minutes), 0) AS total
                FROM focus_sessions
                WHERE substr(completed_at, 1, 10) BETWEEN ? AND ?
                GROUP BY substr(completed_at, 1, 10)
            """, (start.isoformat(), end.isoformat())).fetchall()
            habit_rows = db.execute("""
                SELECT log_date AS day, COUNT(*) AS total
                FROM habit_logs
                WHERE log_date BETWEEN ? AND ?
                GROUP BY log_date
            """, (start.isoformat(), end.isoformat())).fetchall()
        tasks_by_day = {row["day"]: row["total"] for row in task_rows}
        focus_by_day = {row["day"]: row["total"] for row in focus_rows}
        habits_by_day = {row["day"]: row["total"] for row in habit_rows}
        result = []
        for offset in range(7):
            day = start + timedelta(days=offset)
            key = day.isoformat()
            result.append({
                "date": key,
                "label": day.strftime("%a").upper()[:2],
                "quests": int(tasks_by_day.get(key, 0)),
                "focus": int(focus_by_day.get(key, 0)),
                "habits": int(habits_by_day.get(key, 0)),
            })
        return result

    def habit_streak(self, habit_id: int, on_date: date | None = None) -> int:
        """Count consecutive daily check-ins ending today (or the supplied date)."""
        from datetime import timedelta

        current = on_date or date.today()
        with self.connect() as db:
            rows = db.execute(
                "SELECT log_date FROM habit_logs WHERE habit_id = ? ORDER BY log_date DESC",
                (habit_id,),
            ).fetchall()
        completed_days = {row["log_date"] for row in rows}
        # A streak remains alive until today is missed; yesterday's streak
        # should still be visible before the user checks in today.
        if current.isoformat() not in completed_days:
            current -= timedelta(days=1)
        streak = 0
        while current.isoformat() in completed_days:
            streak += 1
            current -= timedelta(days=1)
        return streak

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

"""Backup and portable export helpers for NEXUS."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from nexus.database import Database


TABLES = ("tasks", "habits", "habit_logs", "transactions", "journal_entries", "focus_sessions")


def create_backup(database: Database, destination: str | Path) -> Path:
    """Create a consistent SQLite backup, even while the app is open."""
    target = Path(destination)
    if target.expanduser().resolve() == database.path.expanduser().resolve():
        raise ValueError("Backup destination must be different from the live database")
    target.parent.mkdir(parents=True, exist_ok=True)
    with database.connect() as source:
        with sqlite3.connect(target) as backup:
            source.backup(backup)
    return target


def export_json(database: Database, destination: str | Path) -> Path:
    """Export all app tables as a portable UTF-8 JSON document."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "app": "NEXUS",
        "format_version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "data": {},
    }
    with database.connect() as connection:
        for table in TABLES:
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            payload["data"][table] = [dict(row) for row in rows]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

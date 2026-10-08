"""Backup and portable export helpers for NEXUS."""
from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from nexus.database import Database


TABLES = ("tasks", "habits", "habit_logs", "transactions", "journal_entries", "focus_sessions", "activity_log", "notifications")


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


def create_full_backup(database: Database, destination: str | Path) -> Path:
    """Create a portable archive containing the account registry and every local workspace."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    account_paths = [Path(item["db_path"]) for item in database.list_accounts()]
    files: list[tuple[Path, str]] = []
    if database._accounts_index.exists():
        files.append((database._accounts_index, "accounts/nexus_accounts.db"))
    for item in account_paths:
        if item.exists():
            files.append((item, f"accounts/workspaces/{item.name}"))
    # Keep the original root database too. This preserves data from installations
    # created before multi-account workspaces were introduced.
    if database.path.exists() and database.path.resolve() not in {p.resolve() for p, _ in files}:
        files.append((database.path, f"legacy/{database.path.name}"))

    manifest = {
        "app": "NEXUS",
        "format_version": 2,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "current_workspace": str(database.path),
        "workspace_count": len(account_paths),
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for source, arcname in files:
            archive.write(source, arcname)
    return target

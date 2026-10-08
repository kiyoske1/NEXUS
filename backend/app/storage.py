from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings


def _sqlite_path() -> Path:
    value = settings.database_url.removeprefix("sqlite:///")
    return Path(value).expanduser()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    if not settings.database_url.startswith("sqlite:///"):
        raise RuntimeError("This deployment currently requires SQLite. PostgreSQL adapter is the next migration step.")
    path = _sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

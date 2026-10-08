#!/usr/bin/env python3
"""One-way migration of a NEXUS SQLite server DB into PostgreSQL.

Usage:
  python backend/scripts/migrate_sqlite_to_postgres.py \
    --sqlite backend/nexus_server.db \
    --postgres postgresql://nexus:password@localhost:5432/nexus
"""
from __future__ import annotations

import argparse
import sqlite3

import psycopg
from psycopg.rows import dict_row


TABLES = ("users", "sessions", "devices", "refresh_tokens", "sync_records")


def postgres_schema(conn):
    statements = [
        """CREATE TABLE IF NOT EXISTS users(
            id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, salt TEXT NOT NULL,
            created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sessions(
            token TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS devices(
            id TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS refresh_tokens(
            token TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL, created_at TEXT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)",
        """CREATE TABLE IF NOT EXISTS sync_records(
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity TEXT NOT NULL, client_id TEXT NOT NULL, payload TEXT NOT NULL,
            updated_at TEXT NOT NULL, deleted BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY(user_id, entity, client_id))""",
        "CREATE INDEX IF NOT EXISTS idx_sync_records_updated ON sync_records(user_id, updated_at)",
    ]
    for sql in statements:
        conn.execute(sql)


def migrate(source_path: str, target_url: str) -> None:
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    target = psycopg.connect(target_url, row_factory=dict_row)
    try:
        postgres_schema(target)
        for table in TABLES:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            columns = rows[0].keys()
            names = ",".join(columns)
            placeholders = ",".join(["%s"] * len(columns))
            updates = ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column not in {"id", "token"})
            sql = f"INSERT INTO {table} ({names}) VALUES ({placeholders})"
            if updates:
                sql += f" ON CONFLICT DO UPDATE SET {updates}"
            for row in rows:
                target.execute(sql, [row[column] for column in columns])
            print(f"{table}: {len(rows)} rows")

        target.execute("SELECT setval(pg_get_serial_sequence('users','id'), COALESCE((SELECT MAX(id) FROM users), 1), true)")
        target.commit()
        print("Migration complete. Verify counts before switching production traffic.")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--postgres", required=True)
    args = parser.parse_args()
    migrate(args.sqlite, args.postgres)


if __name__ == "__main__":
    main()

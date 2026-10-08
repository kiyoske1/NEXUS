"""Cloud sync client for NEXUS.

Uses only the Python standard library so the desktop app keeps its dependency
footprint small. The server stores authenticated, per-user sync records.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.request
import urllib.parse
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_PREFIX = "/api/v1"
TABLES = ("tasks", "habits", "habit_logs", "transactions", "journal_entries", "focus_sessions")
SYNC_META = """
CREATE TABLE IF NOT EXISTS sync_meta (
    entity TEXT NOT NULL,
    client_id TEXT NOT NULL,
    local_id INTEGER NOT NULL,
    payload_hash TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY(entity, client_id)
);
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    pushed INTEGER NOT NULL DEFAULT 0,
    pulled INTEGER NOT NULL DEFAULT 0,
    conflicts INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sync_history_started ON sync_history(started_at DESC);
CREATE TABLE IF NOT EXISTS sync_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,
    client_id TEXT NOT NULL,
    local_payload TEXT NOT NULL,
    remote_payload TEXT NOT NULL,
    remote_updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(entity, client_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncError(RuntimeError):
    pass


class SyncClient:
    def __init__(self, database, api_url: str | None = None, token: str | None = None, refresh_token: str | None = None, token_saver=None) -> None:
        self.database = database
        self.api_url = (api_url or os.getenv("NEXUS_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.token = token or ""
        self.refresh_token = refresh_token or ""
        self.token_saver = token_saver
        self._ensure_meta()
        self.device_id = self._load_device_id()
        self.last_sync_at = self._load_last_sync()
        self._lock = threading.RLock()

    def _ensure_meta(self) -> None:
        with self.database.connect() as db:
            db.executescript(SYNC_META)

    def _load_last_sync(self) -> str:
        with self.database.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = db.execute("SELECT value FROM sync_state WHERE key=?", ("last_sync_at",)).fetchone()
            return str(row["value"]) if row else ""

    def _save_last_sync(self, value: str) -> None:
        with self.database.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT INTO sync_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("last_sync_at", value))
            db.commit()
        self.last_sync_at = value

    def _load_device_id(self) -> str:
        # Device identity belongs to the local workspace, not the parent folder.
        # Multiple NEXUS accounts share ~/.nexus, so a single parent-level ID would
        # incorrectly merge their cloud devices.
        path = self.database.path.with_name(self.database.path.name + ".device_id")
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value

        # Preserve the legacy device identity for the original root workspace.
        legacy = self.database.path.parent / "device_id"
        if self.database.path.name == "nexus.db" and legacy.exists():
            value = legacy.read_text(encoding="utf-8").strip()
            if value:
                path.write_text(value, encoding="utf-8")
                return value

        value = str(uuid.uuid4())
        path.write_text(value, encoding="utf-8")
        return value

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(f"{self.api_url}{API_PREFIX}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 401 and path != "/auth/refresh" and self.refresh_token:
                try:
                    refreshed = self._request_raw_refresh()
                    self._set_tokens(refreshed)
                    return self._request(method, path, payload)
                except Exception as refresh_error:
                    self.token = ""
                    self.refresh_token = ""
                    if self.token_saver:
                        self.token_saver("", "")
                    raise SyncError("Cloud session expired. Please sign in again.") from refresh_error
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail", error.reason)
            except Exception:
                detail = error.reason
            raise SyncError(f"API {error.code}: {detail}") from error

        except (urllib.error.URLError, TimeoutError) as error:
            raise SyncError(f"Cannot reach NEXUS API: {error}") from error

    def _request_raw_refresh(self) -> dict[str, Any]:
        body = json.dumps({"refresh_token": self.refresh_token, "device_id": self.device_id}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_url}{API_PREFIX}/auth/refresh", data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def _set_tokens(self, result: dict[str, Any]) -> None:
        self.token = result.get("access_token", "")
        self.refresh_token = result.get("refresh_token", self.refresh_token)
        if result.get("device_id"):
            self.device_id = result["device_id"]
        if self.token_saver:
            self.token_saver(self.token, self.refresh_token)

    def register(self, name: str, email: str, username: str, password: str) -> dict[str, Any]:
        result = self._request("POST", "/auth/register", {
            "name": name, "email": email, "username": username, "password": password, "device_id": self.device_id, "device_name": "NEXUS desktop",
        })
        self._set_tokens(result)
        return result["user"]

    def login(self, username_or_email: str, password: str) -> dict[str, Any]:
        result = self._request("POST", "/auth/login", {
            "username_or_email": username_or_email, "password": password, "device_id": self.device_id, "device_name": "NEXUS desktop",
        })
        self._set_tokens(result)
        return result["user"]

    def logout(self) -> None:
        try:
            if self.token:
                self._request("POST", "/auth/logout")
        finally:
            self.token = ""
            self.refresh_token = ""
            if self.token_saver:
                self.token_saver("", "")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def _records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with self.database.connect() as db:
            for table in TABLES:
                rows = db.execute(f"SELECT * FROM {table}").fetchall()
                for row in rows:
                    payload = dict(row)
                    local_id = int(payload["id"])
                    mapped = db.execute(
                        "SELECT client_id FROM sync_meta WHERE entity=? AND local_id=?",
                        (table, local_id),
                    ).fetchone()
                    client_id = mapped["client_id"] if mapped else f"{self.device_id}:{table}:{local_id}"
                    if table == "habit_logs":
                        habit_map = db.execute(
                            "SELECT client_id FROM sync_meta WHERE entity='habits' AND local_id=?",
                            (int(payload["habit_id"]),),
                        ).fetchone()
                        payload["habit_client_id"] = habit_map["client_id"] if habit_map else self._habit_client_id(db, int(payload["habit_id"]))
                    records.append({"entity": table, "client_id": client_id, "payload": payload, "local_id": local_id})
        return records

    def _habit_client_id(self, db: sqlite3.Connection, habit_id: int) -> str:
        row = db.execute("SELECT id FROM habits WHERE id=?", (habit_id,)).fetchone()
        if not row:
            return ""
        return f"{self.device_id}:habits:{int(row['id'])}"

    @staticmethod
    def _hash(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def list_conflicts(self) -> list[dict[str, Any]]:
        with self.database.connect() as db:
            rows = db.execute("SELECT id, entity, client_id, local_payload, remote_payload, remote_updated_at, created_at FROM sync_conflicts ORDER BY created_at DESC").fetchall()
        return [{**dict(row), "local_payload": json.loads(row["local_payload"]), "remote_payload": json.loads(row["remote_payload"])} for row in rows]

    def resolve_conflict(self, conflict_id: int, choice: str) -> None:
        if choice not in {"local", "remote"}:
            raise SyncError("Conflict choice must be local or remote.")
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM sync_conflicts WHERE id=?", (int(conflict_id),)).fetchone()
        if not row:
            raise SyncError("Conflict no longer exists.")
        payload = json.loads(row["local_payload"] if choice == "local" else row["remote_payload"])
        entity, client_id = row["entity"], row["client_id"]
        if choice == "remote":
            if payload:
                self._upsert_remote(entity, client_id, payload)
            else:
                self._delete_remote(entity, client_id)
        else:
            with self.database.connect() as db:
                meta = db.execute("SELECT local_id FROM sync_meta WHERE entity=? AND client_id=?", (entity, client_id)).fetchone()
                if meta:
                    db.execute("UPDATE sync_meta SET payload_hash=?, synced_at=? WHERE entity=? AND client_id=?", (self._hash(payload), _now(), entity, client_id))
                    db.commit()
        with self.database.connect() as db:
            db.execute("DELETE FROM sync_conflicts WHERE id=?", (int(conflict_id),))
            db.commit()

    def _changed_records(self) -> list[dict[str, Any]]:
        current = self._records()
        with self.database.connect() as db:
            changed = []
            conflicts = {(row["entity"], row["client_id"]) for row in db.execute("SELECT entity, client_id FROM sync_conflicts").fetchall()}
            for record in current:
                if (record["entity"], record["client_id"]) in conflicts:
                    continue
                digest = self._hash(record["payload"])
                old = db.execute(
                    "SELECT payload_hash FROM sync_meta WHERE entity=? AND client_id=?",
                    (record["entity"], record["client_id"]),
                ).fetchone()
                if not old or old["payload_hash"] != digest:
                    changed.append({**record, "hash": digest})
            return changed

    def _tombstones(self) -> list[dict[str, Any]]:
        current = {(r["entity"], r["client_id"]) for r in self._records()}
        with self.database.connect() as db:
            rows = db.execute("SELECT entity, client_id FROM sync_meta").fetchall()
        return [{"entity": r["entity"], "client_id": r["client_id"], "payload": {}, "deleted": True}
                for r in rows if (r["entity"], r["client_id"]) not in current]

    def push(self) -> dict[str, Any]:
        if not self.token:
            raise SyncError("Cloud account is not connected.")
        records = self._changed_records()
        records.extend(self._tombstones())
        wire = []
        for record in records:
            wire.append({
                "entity": record["entity"],
                "client_id": record["client_id"],
                "payload": record["payload"],
                "updated_at": _now(),
                "deleted": record.get("deleted", False),
            })
        result = {"accepted": 0}
        for start in range(0, len(wire), 500):
            chunk = self._request("POST", "/sync/push", {"records": wire[start:start + 500]})
            result["accepted"] += int(chunk.get("accepted", 0))
        now = _now()
        with self.database.connect() as db:
            for record in records:
                if record.get("deleted"):
                    db.execute(
                        "DELETE FROM sync_meta WHERE entity=? AND client_id=?",
                        (record["entity"], record["client_id"]),
                    )
                    continue
                digest = self._hash(record["payload"])
                local_id = int(record.get("local_id", -1))
                db.execute(
                    """INSERT INTO sync_meta(entity,client_id,local_id,payload_hash,synced_at)
                       VALUES(?,?,?,?,?) ON CONFLICT(entity,client_id) DO UPDATE SET
                       local_id=excluded.local_id,payload_hash=excluded.payload_hash,synced_at=excluded.synced_at""",
                    (record["entity"], record["client_id"], local_id, digest, now),
                )
            db.commit()
        return {"accepted": result.get("accepted", 0), "sent": len(records)}



    def list_history(self, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.database.connect() as db:
            rows = db.execute(
                "SELECT id, started_at, finished_at, status, pushed, pulled, conflicts, error "
                "FROM sync_history ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _record_history(self, started_at: str, status: str, pushed: int = 0, pulled: int = 0, conflicts: int = 0, error: str = "") -> None:
        with self.database.connect() as db:
            db.execute(
                "INSERT INTO sync_history(started_at,finished_at,status,pushed,pulled,conflicts,error) VALUES(?,?,?,?,?,?,?)",
                (started_at, _now(), status, int(pushed), int(pulled), int(conflicts), error[:1000]),
            )
            db.commit()

    def _upsert_remote(self, entity: str, client_id: str, payload: dict[str, Any]) -> None:
        table = entity
        if table not in TABLES:
            return
        with self.database.connect() as db:
            # Remote payloads must never control SQL identifiers. Derive the
            # writable columns from the local schema and ignore unknown fields.
            allowed_columns = {
                row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()
            } - {"id"}
            columns = [
                key for key in payload
                if key in allowed_columns and key != "habit_client_id"
            ]
            if not columns:
                raise SyncError("Remote sync record contains no valid fields.")

            existing = db.execute("SELECT local_id FROM sync_meta WHERE entity=? AND client_id=?",
                                  (entity, client_id)).fetchone()
            if existing:
                local_id = int(existing["local_id"])
                values = [payload[key] for key in columns]
                db.execute(f"UPDATE {table} SET {', '.join(f'{column}=?' for column in columns)} WHERE id=?",
                           [*values, local_id])
            else:
                values = [payload[key] for key in columns]
                cursor = db.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
                local_id = int(cursor.lastrowid)
            if table == "habit_logs" and payload.get("habit_client_id"):
                habit = db.execute("SELECT local_id FROM sync_meta WHERE entity='habits' AND client_id=?",
                                   (payload["habit_client_id"],)).fetchone()
                if habit:
                    db.execute("UPDATE habit_logs SET habit_id=? WHERE id=?", (habit["local_id"], local_id))
            digest_payload = dict(payload)
            db.execute(
                """INSERT INTO sync_meta(entity,client_id,local_id,payload_hash,synced_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(entity,client_id) DO UPDATE SET
                   local_id=excluded.local_id,payload_hash=excluded.payload_hash,synced_at=excluded.synced_at""",
                (entity, client_id, local_id, self._hash(digest_payload), _now()),
            )
            db.commit()

    def _delete_remote(self, entity: str, client_id: str) -> None:
        with self.database.connect() as db:
            row = db.execute("SELECT local_id FROM sync_meta WHERE entity=? AND client_id=?",
                             (entity, client_id)).fetchone()
            if not row:
                return
            local_id = int(row["local_id"])
            if entity == "habits":
                db.execute("DELETE FROM habit_logs WHERE habit_id=?", (local_id,))
            db.execute(f"DELETE FROM {entity} WHERE id=?", (local_id,))
            db.execute("DELETE FROM sync_meta WHERE entity=? AND client_id=?", (entity, client_id))
            db.commit()

    def pull(self, since: str | None = None) -> dict[str, Any]:
        if not self.token:
            raise SyncError("Cloud account is not connected.")
        since = since or self.last_sync_at
        query = "" if not since else f"?since={urllib.parse.quote(since)}"
        result = self._request("GET", f"/sync/pull{query}")
        applied = 0
        records = result.get("records", [])
        order = {"habits": 0, "tasks": 1, "transactions": 2, "journal_entries": 3, "focus_sessions": 4, "habit_logs": 5}
        records.sort(key=lambda record: order.get(record.get("entity"), 99))
        for record in records:
            entity, client_id = record["entity"], record["client_id"]
            with self.database.connect() as db:
                meta = db.execute("SELECT local_id, payload_hash FROM sync_meta WHERE entity=? AND client_id=?", (entity, client_id)).fetchone()
                local_payload = None
                if meta and entity in TABLES:
                    local_row = db.execute(f"SELECT * FROM {entity} WHERE id=?", (int(meta["local_id"]),)).fetchone()
                    local_payload = dict(local_row) if local_row else None
            incoming_payload = record.get("payload", {})
            local_changed = meta is not None and local_payload is not None and self._hash(local_payload) != meta["payload_hash"]
            if local_changed:
                with self.database.connect() as db:
                    db.execute("""INSERT INTO sync_conflicts(entity,client_id,local_payload,remote_payload,remote_updated_at,created_at)
                                 VALUES(?,?,?,?,?,?) ON CONFLICT(entity,client_id) DO UPDATE SET
                                 local_payload=excluded.local_payload, remote_payload=excluded.remote_payload,
                                 remote_updated_at=excluded.remote_updated_at""",
                               (entity, client_id, json.dumps(local_payload, ensure_ascii=False),
                                json.dumps(incoming_payload, ensure_ascii=False), record.get("updated_at", ""), _now()))
                    db.commit()
                continue
            if record.get("deleted"):
                self._delete_remote(entity, client_id)
            else:
                self._upsert_remote(entity, client_id, incoming_payload)
            applied += 1
        server_time = result.get("server_time", "")
        if server_time:
            self._save_last_sync(server_time)
        return {"applied": applied, "server_time": server_time}

    def sync(self) -> dict[str, Any]:
        if not self.token:
            raise SyncError("Cloud account is not connected.")
        if not self._lock.acquire(blocking=False):
            raise SyncError("A cloud sync is already running.")
        started_at = _now()
        try:
            pulled = self.pull()
            pushed = self.push()
            conflicts = len(self.list_conflicts())
            result = {"pulled": pulled["applied"], "pushed": pushed["sent"], "accepted": pushed["accepted"], "conflicts": conflicts}
            self._record_history(started_at, "success" if conflicts == 0 else "conflicts", result["pushed"], result["pulled"], conflicts)
            return result
        except Exception as error:
            conflicts = len(self.list_conflicts())
            self._record_history(started_at, "error", conflicts=conflicts, error=str(error))
            raise
        finally:
            self._lock.release()

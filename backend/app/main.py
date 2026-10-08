from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import secrets
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = APP_DIR / "nexus_server.db"
TOKEN_TTL_DAYS = 30
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="NEXUS API", version="0.2.0")


def db():
    path = Path(os.getenv("NEXUS_SERVER_DB", str(DEFAULT_DB_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions(
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS sync_records(
            user_id INTEGER NOT NULL,
            entity TEXT NOT NULL,
            client_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, entity, client_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sync_records_updated
            ON sync_records(user_id, updated_at);
    """)
    conn.commit()
    return conn


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def issue_token(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    conn = db()
    conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)",
                 (token, user_id, expires.isoformat()))
    conn.commit()
    conn.close()
    return token


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    conn = db()
    row = conn.execute(
        """SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
           WHERE s.token=? AND s.expires_at>?""",
        (credentials.credentials, now_utc()),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return dict(row)


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    username: str
    password: str


class LoginIn(BaseModel):
    username_or_email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    username: str
    created_at: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SyncRecordIn(BaseModel):
    entity: str = Field(min_length=1, max_length=64)
    client_id: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)
    updated_at: str | None = None
    deleted: bool = False


class SyncPushIn(BaseModel):
    records: list[SyncRecordIn] = Field(default_factory=list, max_length=500)


@app.get("/health")
def health():
    return {"status": "ok", "service": "nexus-api", "version": app.version}


@app.post("/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn):
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    name, email, username = data.name.strip(), str(data.email).lower().strip(), data.username.strip()
    if not name or not username:
        raise HTTPException(400, "Name and username are required")
    salt = secrets.token_hex(16)
    conn = db()
    try:
        cur = conn.execute(
            """INSERT INTO users(name,email,username,password_hash,salt,created_at)
               VALUES(?,?,?,?,?,?)""",
            (name, email, username, hash_password(data.password, salt), salt, now_utc()),
        )
        conn.commit()
        user_id = cur.lastrowid
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, "Email or username already exists")
    conn.close()
    return {"access_token": issue_token(user_id), "user": dict(row)}


@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn):
    conn = db()
    value = data.username_or_email.strip()
    row = conn.execute(
        "SELECT * FROM users WHERE lower(email)=lower(?) OR lower(username)=lower(?)",
        (value, value),
    ).fetchone()
    conn.close()
    if not row or not secrets.compare_digest(
        hash_password(data.password, row["salt"]), row["password_hash"]
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return {"access_token": issue_token(row["id"]), "user": dict(row)}


@app.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if credentials:
        conn = db()
        conn.execute("DELETE FROM sessions WHERE token=?", (credentials.credentials,))
        conn.commit()
        conn.close()
    return {"ok": True}


@app.get("/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return user


@app.get("/sync")
def sync(user=Depends(current_user)):
    return {"user_id": user["id"], "server_time": now_utc(),
            "message": "Use /sync/pull and /sync/push for data synchronization."}


@app.get("/sync/pull")
def sync_pull(since: str | None = None, user=Depends(current_user)):
    conn = db()
    query = """SELECT entity, client_id, payload, updated_at, deleted
               FROM sync_records WHERE user_id=?"""
    params = [user["id"]]
    if since:
        query += " AND updated_at>?"
        params.append(since)
    query += " ORDER BY updated_at ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {
        "server_time": now_utc(),
        "records": [
            {"entity": r["entity"], "client_id": r["client_id"],
             "payload": json.loads(r["payload"]), "updated_at": r["updated_at"],
             "deleted": bool(r["deleted"])}
            for r in rows
        ],
    }


@app.post("/sync/push")
def sync_push(data: SyncPushIn, user=Depends(current_user)):
    conn = db()
    accepted = 0
    for record in data.records:
        updated_at = record.updated_at or now_utc()
        existing = conn.execute(
            """SELECT updated_at FROM sync_records
               WHERE user_id=? AND entity=? AND client_id=?""",
            (user["id"], record.entity, record.client_id),
        ).fetchone()
        if existing and existing["updated_at"] >= updated_at:
            continue
        conn.execute(
            """INSERT INTO sync_records(user_id,entity,client_id,payload,updated_at,deleted)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id,entity,client_id) DO UPDATE SET
               payload=excluded.payload, updated_at=excluded.updated_at,
               deleted=excluded.deleted""",
            (user["id"], record.entity, record.client_id,
             json.dumps(record.payload, ensure_ascii=False, separators=(",", ":")),
             updated_at, int(record.deleted)),
        )
        accepted += 1
    conn.commit()
    conn.close()
    return {"accepted": accepted, "server_time": now_utc()}

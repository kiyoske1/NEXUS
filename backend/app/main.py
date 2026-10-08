from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import secrets
import sqlite3

from .config import settings
from .storage import connect
import uuid

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = APP_DIR / "nexus_server.db"
TOKEN_TTL_MINUTES = settings.access_token_minutes
REFRESH_TTL_DAYS = settings.refresh_token_days
bearer = HTTPBearer(auto_error=False)
API_VERSION = "1.0.0"
API_PREFIX = "/api/v1"
LEGACY_PATHS = {
    "/health", "/auth/register", "/auth/login", "/auth/refresh", "/auth/logout",
    "/auth/logout-all", "/me", "/devices", "/sync", "/sync/pull", "/sync/push",
}

app = FastAPI(
    title="NEXUS API",
    version=API_VERSION,
    docs_url=f"{API_PREFIX}/docs",
    redoc_url=f"{API_PREFIX}/redoc",
    openapi_url=f"{API_PREFIX}/openapi.json",
)
api = APIRouter(prefix=API_PREFIX, tags=["v1"])

@app.middleware("http")
async def legacy_api_redirect(request: Request, call_next):
    path = request.scope.get("path", "")
    if path in LEGACY_PATHS or any(path.startswith(prefix + "/") for prefix in LEGACY_PATHS):
        request.scope["path"] = f"{API_PREFIX}{path}"
        request.scope["raw_path"] = request.scope["path"].encode("utf-8")
        response = await call_next(request)
        response.headers["X-NEXUS-API-Version"] = API_VERSION
        response.headers["Deprecation"] = "true"
        return response
    response = await call_next(request)
    if request.scope.get("path", "").startswith(API_PREFIX):
        response.headers["X-NEXUS-API-Version"] = API_VERSION
    return response


if settings.cors_origins:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def db():
    return connect()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def issue_tokens(user_id: int, device_id: str | None = None, device_name: str = "NEXUS device") -> tuple[str, str, str]:
    access_token = secrets.token_urlsafe(48)
    refresh_token = secrets.token_urlsafe(64)
    device_id = device_id or str(uuid.uuid4())
    now = now_utc()
    access_expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    refresh_expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS)
    conn = db()
    conn.execute(
        "INSERT INTO devices(id,user_id,name,created_at,last_seen_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, last_seen_at=excluded.last_seen_at",
        (device_id, user_id, device_name.strip() or "NEXUS device", now, now),
    )
    conn.execute(
        "INSERT INTO sessions(token,user_id,device_id,expires_at) VALUES(?,?,?,?)",
        (access_token, user_id, device_id, access_expires.isoformat()),
    )
    conn.execute(
        "INSERT INTO refresh_tokens(token,user_id,device_id,expires_at,created_at) VALUES(?,?,?,?,?)",
        (refresh_token, user_id, device_id, refresh_expires.isoformat(), now),
    )
    conn.commit()
    conn.close()
    return access_token, refresh_token, device_id


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    conn = db()
    row = conn.execute(
        """SELECT u.*, s.device_id AS session_device_id FROM users u
           JOIN sessions s ON s.user_id=u.id
           WHERE s.token=? AND s.expires_at>?""",
        (credentials.credentials, now_utc()),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if row["session_device_id"]:
        conn.execute(
            "UPDATE devices SET last_seen_at=? WHERE id=? AND user_id=?",
            (now_utc(), row["session_device_id"], row["id"]),
        )
        conn.commit()
    user = dict(row)
    conn.close()
    return user


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    username: str
    password: str
    device_id: str | None = None
    device_name: str = "NEXUS desktop"


class LoginIn(BaseModel):
    username_or_email: str
    password: str
    device_id: str | None = None
    device_name: str = "NEXUS desktop"


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    username: str
    created_at: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    device_id: str
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20)
    device_id: str | None = None


class DeviceOut(BaseModel):
    id: str
    name: str
    created_at: str
    last_seen_at: str
    current: bool = False


class DeviceUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SyncRecordIn(BaseModel):
    entity: str = Field(min_length=1, max_length=64)
    client_id: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)
    updated_at: str | None = None
    deleted: bool = False


class SyncPushIn(BaseModel):
    records: list[SyncRecordIn] = Field(default_factory=list, max_length=500)


@api.get("/health")
def health():
    return {"status": "ok", "service": "nexus-api", "version": app.version}


@api.post("/auth/register", response_model=TokenOut, status_code=201)
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
    access_token, refresh_token, device_id = issue_tokens(user_id, data.device_id, data.device_name)
    return {"access_token": access_token, "refresh_token": refresh_token, "device_id": device_id, "user": dict(row)}


@api.post("/auth/login", response_model=TokenOut)
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
    access_token, refresh_token, device_id = issue_tokens(row["id"], data.device_id, data.device_name)
    return {"access_token": access_token, "refresh_token": refresh_token, "device_id": device_id, "user": dict(row)}


@api.post("/auth/refresh", response_model=TokenOut)
def refresh(data: RefreshIn):
    conn = db()
    row = conn.execute(
        """SELECT r.*, u.* FROM refresh_tokens r
           JOIN users u ON u.id=r.user_id
           WHERE r.token=? AND r.expires_at>?""",
        (data.refresh_token, now_utc()),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    if data.device_id and row["device_id"] != data.device_id:
        conn.close()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token device mismatch")
    conn.execute("DELETE FROM refresh_tokens WHERE token=?", (data.refresh_token,))
    conn.commit()
    conn.close()
    access_token, refresh_token, device_id = issue_tokens(
        row["user_id"], row["device_id"], row["name"] or "NEXUS device"
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "device_id": device_id,
        "user": dict(row),
    }


@api.get("/devices", response_model=list[DeviceOut])
def devices(user=Depends(current_user)):
    conn = db()
    rows = conn.execute(
        "SELECT id,name,created_at,last_seen_at FROM devices WHERE user_id=? ORDER BY last_seen_at DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    return [{**dict(r), "current": r["id"] == user.get("session_device_id")} for r in rows]


@api.patch("/devices/{device_id}", response_model=DeviceOut)
def rename_device(device_id: str, data: DeviceUpdateIn, user=Depends(current_user)):
    name = data.name.strip()
    conn = db()
    row = conn.execute("SELECT id,name,created_at,last_seen_at FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Device not found")
    conn.execute("UPDATE devices SET name=? WHERE id=? AND user_id=?", (name, device_id, user["id"]))
    conn.commit()
    updated = conn.execute("SELECT id,name,created_at,last_seen_at FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
    conn.close()
    return {**dict(updated), "current": device_id == user.get("session_device_id")}


@api.delete("/devices/{device_id}")
def revoke_device(device_id: str, user=Depends(current_user)):
    conn = db()
    row = conn.execute(
        "SELECT id FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Device not found")
    conn.execute("DELETE FROM sessions WHERE user_id=? AND device_id=?", (user["id"], device_id))
    conn.execute("DELETE FROM refresh_tokens WHERE user_id=? AND device_id=?", (user["id"], device_id))
    conn.execute("DELETE FROM devices WHERE id=? AND user_id=?", (device_id, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


@api.post("/auth/logout-all")
def logout_all(user=Depends(current_user)):
    conn = db()
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    conn.execute("DELETE FROM refresh_tokens WHERE user_id=?", (user["id"],))
    conn.commit()
    conn.close()
    return {"ok": True}


@api.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        return {"ok": True}
    conn = db()
    row = conn.execute(
        "SELECT user_id, device_id FROM sessions WHERE token=?",
        (credentials.credentials,),
    ).fetchone()
    conn.execute("DELETE FROM sessions WHERE token=?", (credentials.credentials,))
    if row and row["device_id"]:
        conn.execute(
            "DELETE FROM refresh_tokens WHERE user_id=? AND device_id=?",
            (row["user_id"], row["device_id"]),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@api.get("/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return user


@api.get("/sync")
def sync(user=Depends(current_user)):
    return {"user_id": user["id"], "server_time": now_utc(),
            "message": "Use /sync/pull and /sync/push for data synchronization."}


@api.get("/sync/pull")
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


@api.post("/sync/push")
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


@api.get("", tags=["v1"])
def api_root():
    return {
        "service": "nexus-api",
        "version": API_VERSION,
        "status": "ok",
        "docs": f"{API_PREFIX}/docs",
        "openapi": f"{API_PREFIX}/openapi.json",
    }


app.include_router(api)

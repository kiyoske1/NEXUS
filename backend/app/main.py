from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib, os, secrets, sqlite3

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

APP_DIR = Path(__file__).resolve().parent.parent
DB_PATH = APP_DIR / "nexus_server.db"
TOKEN_TTL_DAYS = 30
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="NEXUS API", version="0.1.0")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )""")
    conn.commit()
    return conn

def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()

def issue_token(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    conn = db()
    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token, user_id, expires.isoformat()))
    conn.commit(); conn.close()
    return token

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    conn = db()
    row = conn.execute("""SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                          WHERE s.token=? AND s.expires_at>?""",
                       (credentials.credentials, datetime.now(timezone.utc).isoformat())).fetchone()
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

@app.get("/health")
def health():
    return {"status": "ok", "service": "nexus-api"}

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
        cur = conn.execute("""INSERT INTO users(name,email,username,password_hash,salt,created_at)
                              VALUES(?,?,?,?,?,?)""",
                           (name,email,username,hash_password(data.password,salt),salt,
                            datetime.now(timezone.utc).isoformat()))
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, "Email or username already exists")
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    token = issue_token(user_id)
    return {"access_token": token, "user": dict(row)}

@app.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?) OR lower(username)=lower(?)",
                       (data.username_or_email.strip(), data.username_or_email.strip())).fetchone()
    conn.close()
    if not row or not secrets.compare_digest(hash_password(data.password, row["salt"]), row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return {"access_token": issue_token(row["id"]), "user": dict(row)}

@app.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if credentials:
        conn=db(); conn.execute("DELETE FROM sessions WHERE token=?", (credentials.credentials,)); conn.commit(); conn.close()
    return {"ok": True}

@app.get("/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return user

@app.get("/sync")
def sync(user=Depends(current_user)):
    return {"user_id": user["id"], "server_time": datetime.now(timezone.utc).isoformat(),
            "message": "Sync transport is ready; desktop data sync comes next."}

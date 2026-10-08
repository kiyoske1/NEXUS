# NEXUS Backend

FastAPI service for NEXUS accounts and future cross-device sync.

## Run locally

From the repository root:

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: `http://127.0.0.1:8000/docs`

## Current API

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /me`
- `GET /sync`

The backend is deliberately separated from the desktop SQLite database. This gives NEXUS a clean path to Android/iOS clients and cloud persistence without pretending local authentication is cloud authentication.


## PostgreSQL deployment

Set `NEXUS_DATABASE_URL` to a PostgreSQL connection string. The Docker stack in `backend/docker-compose.yml` runs PostgreSQL, the API, and Caddy with automatic HTTPS.

For an existing SQLite server database, make a backup first and run:

    python backend/scripts/migrate_sqlite_to_postgres.py --sqlite backend/nexus_server.db --postgres "postgresql://nexus:PASSWORD@HOST:5432/nexus"

Verify row counts before switching production traffic.

## Cloud sessions

Access tokens are short-lived. Desktop NEXUS keeps a refresh token and automatically rotates it after a `401` response. On Windows, cloud credentials are protected with Windows DPAPI instead of being stored as plain QSettings values.

The sync client also persists the last successful server cursor so routine syncs request only records changed since the previous pull.

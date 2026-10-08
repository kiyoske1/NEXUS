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

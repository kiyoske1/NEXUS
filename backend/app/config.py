from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("NEXUS_DATABASE_URL") or ("sqlite:///" + os.getenv("NEXUS_SERVER_DB") if os.getenv("NEXUS_SERVER_DB") else "sqlite:///./nexus_server.db")
    jwt_secret: str = os.getenv("NEXUS_JWT_SECRET", "change-me-in-production")
    access_token_minutes: int = int(os.getenv("NEXUS_ACCESS_TOKEN_MINUTES", "30"))
    refresh_token_days: int = int(os.getenv("NEXUS_REFRESH_TOKEN_DAYS", "30"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("NEXUS_CORS_ORIGINS", "").split(",") if origin.strip()
    )


settings = Settings()

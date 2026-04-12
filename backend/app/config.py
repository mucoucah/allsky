"""Runtime configuration for allsky-web.

All paths default to the upstream Allsky layout (~/allsky/...) but can be
overridden via environment variables for development or non-standard installs.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    # Where the existing (upstream) Allsky lives. We never write outside this
    # tree except for our own database in DATA_DIR.
    allsky_home: Path = Path(os.environ.get("ALLSKY_HOME", str(Path.home() / "allsky")))

    # Where allsky-web stores its own state (sqlite db, sessions, etc).
    data_dir: Path = Path(
        os.environ.get("ALLSKY_WEB_DATA", str(Path(__file__).resolve().parents[2] / "data"))
    )

    # HTTP server bind.
    host: str = os.environ.get("ALLSKY_WEB_HOST", "127.0.0.1")
    port: int = int(os.environ.get("ALLSKY_WEB_PORT", "8000"))

    # Session signing key. Generate a real one for production.
    session_secret: str = os.environ.get(
        "ALLSKY_WEB_SECRET", "dev-only-change-me-in-production"
    )

    # If set, require this username/password (bcrypt hash) for the WebUI.
    # Empty username disables auth (useful for trusted LAN-only setups).
    auth_user: str = os.environ.get("ALLSKY_WEB_USER", "")
    auth_pass_hash: str = os.environ.get("ALLSKY_WEB_PASS_HASH", "")

    # Live-view broadcast cadence cap (Hz). The actual rate is limited by the
    # capture loop, but we throttle to avoid hammering slow clients.
    live_max_fps: float = float(os.environ.get("ALLSKY_WEB_LIVE_MAX_FPS", "2.0"))

    # CORS origins for development (when frontend Vite dev-server runs separately).
    cors_origins: list[str] = (
        os.environ.get("ALLSKY_WEB_CORS", "http://localhost:5173").split(",")
        if os.environ.get("ALLSKY_WEB_CORS", "http://localhost:5173")
        else []
    )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s

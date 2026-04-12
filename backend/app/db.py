"""SQLite metadata layer (aiosqlite).

We keep this narrow on purpose: source of truth for *settings* stays
Allsky's settings.json. The DB stores only:
  - images_meta: indexed view of images/YYYYMMDD/ for fast filtering
  - alerts: notifications surfaced in the UI
  - settings_audit: who-changed-what trail
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from app.config import get_settings

log = logging.getLogger(__name__)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS images_meta (
        path TEXT PRIMARY KEY,
        date_dir TEXT NOT NULL,
        filename TEXT NOT NULL,
        captured_at REAL NOT NULL,
        size_bytes INTEGER NOT NULL,
        width INTEGER,
        height INTEGER,
        exposure_us INTEGER,
        iso INTEGER,
        has_thumbnail INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_images_meta_date ON images_meta(date_dir)",
    "CREATE INDEX IF NOT EXISTS idx_images_meta_captured ON images_meta(captured_at)",
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at REAL NOT NULL,
        acknowledged_at REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at)",
    """
    CREATE TABLE IF NOT EXISTS settings_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        actor TEXT,
        key TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT
    )
    """,
]


def db_path() -> Path:
    return get_settings().data_dir / "allskyweb.sqlite"


@asynccontextmanager
async def connect():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(p))
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


async def init_db() -> None:
    async with connect() as conn:
        for stmt in SCHEMA:
            await conn.execute(stmt)
        await conn.commit()
    log.info("db: initialised at %s", db_path())


# --- helpers used by routers ---

async def upsert_image(conn, rec) -> None:
    await conn.execute(
        """
        INSERT INTO images_meta(path, date_dir, filename, captured_at,
                                size_bytes, width, height, exposure_us, iso, has_thumbnail)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            captured_at=excluded.captured_at,
            size_bytes=excluded.size_bytes,
            width=excluded.width,
            height=excluded.height,
            exposure_us=excluded.exposure_us,
            iso=excluded.iso,
            has_thumbnail=excluded.has_thumbnail
        """,
        (
            rec.path,
            rec.date_dir,
            rec.filename,
            rec.captured_at,
            rec.size_bytes,
            rec.width,
            rec.height,
            rec.exposure_us,
            rec.iso,
            1 if rec.has_thumbnail else 0,
        ),
    )


async def insert_alert(level: str, source: str, message: str) -> int:
    import time
    async with connect() as conn:
        cur = await conn.execute(
            "INSERT INTO alerts(level, source, message, created_at) VALUES(?, ?, ?, ?)",
            (level, source, message, time.time()),
        )
        await conn.commit()
        return cur.lastrowid or 0


async def log_setting_change(actor: str | None, key: str, old, new) -> None:
    import json
    import time
    async with connect() as conn:
        await conn.execute(
            "INSERT INTO settings_audit(ts, actor, key, old_value, new_value) VALUES(?, ?, ?, ?, ?)",
            (time.time(), actor, key, json.dumps(old), json.dumps(new)),
        )
        await conn.commit()

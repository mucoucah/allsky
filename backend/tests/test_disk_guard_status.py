"""System status exposes the disk guard, and the alert is raised once."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_system_status_reports_retention_and_guard(monkeypatch):
    home = Path(os.environ["ALLSKY_HOME"])
    data = home / "data"
    (home / "config").mkdir(parents=True, exist_ok=True)
    config = home / "config" / "offload.json"
    config.write_text(json.dumps({
        "mode": "capture-only",
        "processor": {
            "data_dir": str(data),
            "incoming_dir": str(home / "incoming"),
            "raw_retention_days": 21,
            "min_free_gb": 12,
        },
    }))
    monkeypatch.setenv("ALLSKY_OFFLOAD_CONFIG", str(config))
    state = data / "config" / "processor_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "disk_guard": {"active": True, "free_gb": 3.5, "since": "2026-11-18T00:00:00+00:00"},
    }))

    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as client:
        got = client.get("/api/system")
        assert got.status_code == 200, got.text
        storage = got.json()["storage"]
        assert storage["raw_retention_days"] == 21
        assert storage["min_free_gb"] == 12
        assert storage["free_bytes"] > 0
        assert storage["data_dir"] == str(data)
        assert storage["disk_guard"]["active"] is True
        assert storage["disk_guard"]["since"] == "2026-11-18T00:00:00+00:00"


def test_disk_guard_alert_is_raised_once(monkeypatch):
    home = Path(os.environ["ALLSKY_HOME"])
    data = home / "guard-data"
    (home / "config").mkdir(parents=True, exist_ok=True)
    config = home / "config" / "offload.json"
    config.write_text(json.dumps({
        "processor": {"data_dir": str(data), "incoming_dir": str(home / "incoming")},
    }))
    monkeypatch.setenv("ALLSKY_OFFLOAD_CONFIG", str(config))
    state = data / "config" / "processor_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "disk_guard": {"active": True, "free_gb": 2.0, "since": "2026-11-18T02:00:00+00:00"},
    }))

    from app.config import get_settings
    get_settings.cache_clear()
    from app.db import connect, init_db
    from app.notify.watchers import poll_disk_guard

    async def alerts() -> list[dict]:
        async with connect() as conn:
            cur = await conn.execute(
                "SELECT level, source, message FROM alerts WHERE source = 'disk' ORDER BY id"
            )
            return [dict(row) for row in await cur.fetchall()]

    async def scenario() -> None:
        await init_db()
        async with connect() as conn:
            await conn.execute("DELETE FROM alerts")
            await conn.execute("DELETE FROM alert_dedup")
            await conn.commit()
        await poll_disk_guard()
        await poll_disk_guard()
        disk = await alerts()
        assert len(disk) == 1
        assert disk[0]["level"] == "warning"
        assert "Raw frames are not being stored" in disk[0]["message"]

        state.write_text(json.dumps({
            "disk_guard": {"active": False, "free_gb": 20.0, "since": "2026-11-18T02:00:00+00:00"},
        }))
        await poll_disk_guard()
        await poll_disk_guard()
        disk = await alerts()
        assert len(disk) == 2
        assert any(item["level"] == "info" and "stored again" in item["message"] for item in disk)

    asyncio.run(scenario())

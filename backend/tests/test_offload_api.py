"""Offload HTTP API: defaults, save, and an empty heartbeat."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_offload_round_trip(monkeypatch):
    home = Path(os.environ["ALLSKY_HOME"])
    (home / "config").mkdir(parents=True, exist_ok=True)
    incoming = home / "incoming"
    incoming.mkdir()
    monkeypatch.setenv("ALLSKY_OFFLOAD_CONFIG", str(home / "config" / "offload.json"))

    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as client:
        got = client.get("/api/offload")
        assert got.status_code == 200
        body = got.json()
        assert body["mode"] == "normal"
        assert body["jpeg_quality"] == 90
        assert body["processor"]["raw_retention_days"] == 14
        assert body["processor"]["min_free_gb"] == 10

        body["mode"] = "capture-only"
        body["jpeg_quality"] = 90
        body["remote"]["host"] = "192.168.1.20"
        body["remote"]["bandwidth_limit_kbps"] = 2000
        body["processor"]["incoming_dir"] = str(incoming)
        body["processor"]["to_pi_dir"] = str(home / "to-pi")
        saved = client.put("/api/offload", json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()["mode"] == "capture-only"

        stored = json.loads((home / "config" / "offload.json").read_text())
        assert stored["remote"]["host"] == "192.168.1.20"
        push = json.loads((home / "to-pi" / "offload-push.json").read_text())
        assert push["bandwidth_limit_kbps"] == 2000
        assert "ssh_key" not in push

        missing = client.get("/api/offload/pi")
        assert missing.status_code == 200
        assert missing.json()["ok"] is False

        status = incoming / "status" / "pi-status.json"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(json.dumps({
            "timestamp": "2026-11-17T22:00:00+00:00",
            "temp_c": 51.5,
            "thermal_state": "ok",
            "outbox_files": 3,
            "camera_error": None,
        }))
        heart = client.get("/api/offload/pi")
        assert heart.status_code == 200
        assert heart.json()["status"]["temp_c"] == 51.5

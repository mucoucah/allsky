"""Read-only meteor hit archive and thumbnail size defaults."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_meteor_hits_list_crop_and_reject_traversal():
    home = Path(os.environ["ALLSKY_HOME"])
    day = home / "html" / "allsky" / "meteors" / "20261117"
    day.mkdir(parents=True, exist_ok=True)
    (day / "meteor_20261117_220000.jpg").write_bytes(b"\xff\xd8\xff full")
    (day / "meteor_20261117_220000_crop.jpg").write_bytes(b"\xff\xd8\xff crop")
    (day / "meteor_20261117_220000.json").write_text(json.dumps({
        "time": "2026-11-17T22:00:00+00:00",
        "meteor_count": 1,
        "lines": [{"x1": 10, "y1": 20, "x2": 100, "y2": 80}],
        "frame": "meteor_20261117_220000.jpg",
        "crop": "meteor_20261117_220000_crop.jpg",
    }))

    from app.config import get_settings
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as client:
        listed = client.get("/api/notifications/meteor/hits")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] >= 1
        hit = next(item for item in body["hits"] if item["id"] == "meteor_20261117_220000")
        assert hit["meteor_count"] == 1
        assert hit["crop_url"].endswith("name=meteor_20261117_220000_crop.jpg")
        assert hit["frame_url"].endswith("name=meteor_20261117_220000.jpg")

        crop = client.get(hit["crop_url"])
        assert crop.status_code == 200
        assert crop.content.startswith(b"\xff\xd8")

        full = client.get(hit["frame_url"])
        assert full.status_code == 200
        assert b"full" in full.content

        bad = client.get(
            "/api/notifications/meteor/hits/file",
            params={"date": "20261117", "name": "../secrets.jpg"},
        )
        assert bad.status_code == 400
        missing = client.get(
            "/api/notifications/meteor/hits/file",
            params={"date": "20261117", "name": "meteor_missing.jpg"},
        )
        assert missing.status_code == 404
    get_settings.cache_clear()


def test_missing_thumbnail_sizes_default():
    from app.config import get_settings
    from app.allsky.settings import load_values

    target = get_settings().web_config_dir / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    original = target.read_text() if target.exists() else None
    target.write_text('{"nightexposure": 8000}\n')
    try:
        values = load_values()
        assert values["thumbnailsizex"] == 100
        assert values["thumbnailsizey"] == 75
        assert values["nightexposure"] == 8000
    finally:
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(original)

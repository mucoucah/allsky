"""Read the upstream status.json + messages.txt for state surfacing."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .paths import paths


def read_status() -> dict[str, Any]:
    """Return the parsed status.json or a synthesised "unknown" record."""
    p = paths().status_file
    if not p.exists():
        return {"status": "Unknown", "raw": None}
    try:
        with p.open() as f:
            data = json.load(f)
        # Upstream stores {"status": "...", "lastchanged": "..."} (varies by version).
        if isinstance(data, dict):
            return {"status": data.get("status", "Unknown"), "raw": data}
        return {"status": str(data), "raw": data}
    except (json.JSONDecodeError, OSError):
        return {"status": "Unknown", "raw": None}


def read_messages(limit: int = 50) -> list[dict[str, Any]]:
    """Parse messages.txt — each non-empty line is a tab-separated record:
    type \t timestamp \t id \t html-message ..."""
    p = paths().messages_file
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with p.open() as f:
            for line in f.readlines()[-limit:]:
                line = line.rstrip("\n")
                if not line:
                    continue
                parts = line.split("\t", 3)
                while len(parts) < 4:
                    parts.append("")
                msg_type, ts, msg_id, body = parts
                out.append(
                    {
                        "type": msg_type or "info",
                        "timestamp": ts,
                        "id": msg_id,
                        "message": body,
                    }
                )
    except OSError:
        return out
    return out


def read_version() -> str:
    p = paths().version_file
    if not p.exists():
        return "unknown"
    try:
        return p.read_text().splitlines()[0].strip()
    except OSError:
        return "unknown"


def read_camera_info() -> dict[str, Any]:
    """Best-effort camera detection from connected_cameras.txt + settings.json."""
    out: dict[str, Any] = {"connected": [], "active": None, "active_model": None}
    p = paths().connected_cameras
    if p.exists():
        try:
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                out["connected"].append(line)
        except OSError:
            pass

    sp = paths().settings_file
    if sp.exists():
        try:
            with sp.open() as f:
                s = json.load(f)
            out["active"] = s.get("cameratype")
            out["active_model"] = s.get("cameramodel")
        except (json.JSONDecodeError, OSError):
            pass
    return out


def latest_image_meta() -> dict[str, Any] | None:
    """Cheap stat-only metadata for the live frame; full EXIF lives in routers/live.py."""
    p = paths().latest_image
    if not p.exists():
        return None
    try:
        st = p.stat()
        return {
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }
    except OSError:
        return None

"""Small status document the Pi uploads for the PC web UI.

The file is JSON and stays small (temperature, throttle bits, disk, last
frame, the newest camera error). It is not a frame and is never deleted to
make room in the outbox.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

THROTTLE_RE = re.compile(r"0x([0-9a-fA-F]+)")


def parse_throttled(text: str | None) -> dict[str, Any]:
    match = THROTTLE_RE.search(text or "")
    value = int(match.group(1), 16) if match else 0
    return {
        "raw": f"0x{value:x}",
        "under_voltage_now": bool(value & 0x1),
        "freq_capped_now": bool(value & 0x2),
        "throttled_now": bool(value & 0x4),
        "soft_temp_limit_now": bool(value & 0x8),
        "any_now": bool(value & 0xF),
    }


def last_camera_error(text: str | None) -> str | None:
    last = None
    for line in (text or "").splitlines():
        lowered = line.lower()
        if "error" not in lowered:
            continue
        if any(word in lowered for word in ("capture", "camera", "rpicam", "libcamera", "imx")):
            cleaned = line.strip()
            if cleaned:
                last = cleaned[:500]
    return last


def read_temp_c(path: Path | None = None) -> float | None:
    zone = path or Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        raw = zone.read_text().strip()
        return int(raw) / 1000.0
    except (OSError, ValueError):
        return None


def disk_report(path: Path) -> dict[str, Any]:
    target = path if path.exists() else Path("/")
    usage = shutil.disk_usage(target)
    percent = round(100.0 * usage.used / usage.total, 1) if usage.total else 0.0
    return {
        "path": str(target),
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": percent,
    }


def build_status(
    *,
    now: datetime | None = None,
    temp_c: float | None,
    throttled_text: str | None,
    disk: dict[str, Any],
    outbox_bytes: int,
    outbox_files: int,
    last_frame_time: str | None,
    last_frame_name: str | None,
    camera_error: str | None,
    thermal_state: str | None,
    mode: str,
    hostname: str | None = None,
) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    throttle = parse_throttled(throttled_text)
    return {
        "timestamp": moment.isoformat(timespec="seconds"),
        "hostname": hostname or os.uname().nodename,
        "mode": mode,
        "temp_c": temp_c,
        "throttled": throttle,
        "disk": disk,
        "outbox_bytes": int(outbox_bytes),
        "outbox_files": int(outbox_files),
        "last_frame_time": last_frame_time,
        "last_frame_name": last_frame_name,
        "camera_error": camera_error,
        "thermal_state": thermal_state or "unknown",
    }


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)


def read_thermal_state(tmp_dir: Path) -> str | None:
    path = tmp_dir / "thermal_guard"
    try:
        text = path.read_text().strip().split()
    except OSError:
        return None
    return text[0] if text else None


def tail_text(path: Path, max_bytes: int = 16_384) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-max_bytes:].decode(errors="replace")

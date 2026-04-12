"""Camera detection and first-time setup helpers.

Probes for connected cameras via rpicam/libcamera and provides
the data needed for the setup wizard in the web UI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .paths import paths

log = logging.getLogger(__name__)


async def detect_cameras() -> list[dict[str, Any]]:
    """Detect connected cameras via libcamera-hello --list-cameras.

    Returns a list of dicts like:
      [{"index": 0, "model": "imx462", "modes": ["1920x1080"], "raw": "..."}]
    """
    cameras: list[dict[str, Any]] = []

    # Try rpicam-hello first (Bookworm), fall back to libcamera-hello (Bullseye).
    for cmd in ["rpicam-hello", "libcamera-hello"]:
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd, "--list-cameras",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = (stdout or b"").decode(errors="replace") + (stderr or b"").decode(errors="replace")
            if proc.returncode == 0 or "Available cameras" in output:
                cameras = _parse_camera_list(output)
                break
        except (FileNotFoundError, asyncio.TimeoutError):
            continue
        except Exception:
            log.exception("camera detection via %s failed", cmd)
            continue

    return cameras


def _parse_camera_list(output: str) -> list[dict[str, Any]]:
    """Parse the output of `libcamera-hello --list-cameras`.

    Example output:
        Available cameras
        -----------------
        0 : imx462 [1920x1080 10-bit RGGB] (/base/soc/i2c0mux/...)
            Modes: 'SRGGB10_CSI2P' : 1920x1080 [10.00 fps - (0, 0)/1920x1080 ...]
    """
    cameras = []
    current: dict[str, Any] | None = None

    for line in output.splitlines():
        # Camera header line: "0 : imx462 [1920x1080 ...]"
        m = re.match(r"^\s*(\d+)\s*:\s*(\S+)\s*\[(.+?)\]", line)
        if m:
            if current:
                cameras.append(current)
            current = {
                "index": int(m.group(1)),
                "model": m.group(2),
                "info": m.group(3),
                "modes": [],
                "raw": line.strip(),
            }
            continue

        # Mode line: resolution from "Modes:" lines.
        if current and "x" in line:
            res_matches = re.findall(r"(\d{3,4}x\d{3,4})", line)
            for r in res_matches:
                if r not in current["modes"]:
                    current["modes"].append(r)

    if current:
        cameras.append(current)
    return cameras


async def setup_initial_config(
    camera_type: str = "RPi",
    camera_model: str = "",
    camera_number: int = 0,
    latitude: str = "",
    longitude: str = "",
) -> dict[str, Any]:
    """Write a minimal settings.json for first-time use.

    Called by the setup wizard when the user configures their camera
    for the first time via the web UI.
    """
    p = paths()
    settings_path = p.settings_file

    # Load existing or start fresh.
    settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            with settings_path.open() as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    settings.update({
        "cameratype": camera_type,
        "cameramodel": camera_model,
        "cameranumber": str(camera_number),
        "filename": "image.jpg",
        "debuglevel": "1",
        "latitude": latitude,
        "longitude": longitude,
        "lastchanged": "1",  # Tells allsky.sh that settings have been reviewed.
    })

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w") as f:
        json.dump(settings, f, indent=4)

    # Update status to indicate configuration is done.
    status_path = p.status_file
    with status_path.open("w") as f:
        json.dump({"status": "Not Running"}, f)

    return {"ok": True, "settings_path": str(settings_path)}

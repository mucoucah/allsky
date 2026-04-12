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
    errors: list[str] = []

    # Try rpicam-hello first (Bookworm), fall back to libcamera-hello (Bullseye).
    for cmd in ["rpicam-hello", "libcamera-hello"]:
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd, "--list-cameras",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = (stdout or b"").decode(errors="replace") + (stderr or b"").decode(errors="replace")
            log.info("camera detect (%s): rc=%s output=%s", cmd, proc.returncode, output[:500])

            if proc.returncode == 0 or "Available cameras" in output:
                cameras = _parse_camera_list(output)
                if cameras:
                    break
                # Command succeeded but no cameras listed.
                if "No cameras available" in output or "No cameras" in output:
                    errors.append(f"{cmd}: no cameras found")
                    break
                # Might have cameras but parsing failed — try next command.
                errors.append(f"{cmd}: ran OK but no cameras parsed from output")
            else:
                errors.append(f"{cmd}: exit code {proc.returncode}")
                if "permission" in output.lower():
                    errors.append("Permission denied — the service user may need 'video' group access")
        except FileNotFoundError:
            continue
        except asyncio.TimeoutError:
            errors.append(f"{cmd}: timed out after 15s")
        except Exception as e:
            log.exception("camera detection via %s failed", cmd)
            errors.append(f"{cmd}: {e}")

    # Also try v4l2 as fallback for USB cameras.
    if not cameras:
        try:
            proc = await asyncio.create_subprocess_exec(
                "v4l2-ctl", "--list-devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = (stdout or b"").decode(errors="replace")
            if output.strip():
                log.info("v4l2 devices: %s", output[:500])
                # Parse basic v4l2 output for ZWO/USB cameras.
                for line in output.splitlines():
                    line = line.strip()
                    if line and not line.startswith("/dev/"):
                        # Device name line (e.g. "ZWO ASI462MC (usb-...):")
                        cameras.append({
                            "index": len(cameras),
                            "model": line.rstrip(":").strip(),
                            "info": "USB camera (v4l2)",
                            "modes": [],
                            "raw": line,
                        })
        except (FileNotFoundError, asyncio.TimeoutError):
            pass

    if errors and not cameras:
        log.warning("camera detection failed: %s", "; ".join(errors))

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
    from .settings import load_values, save_values

    # Load existing or start fresh.
    settings = load_values()

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

    # Write to both web config and allsky home copies.
    save_values(settings)

    # Update status to indicate configuration is done.
    p = paths()
    for status_path in (p.status_file, p.config / "status.json"):
        try:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            with status_path.open("w") as f:
                json.dump({"status": "Not Running"}, f)
        except OSError:
            pass

    log.info("setup_initial_config: camera_type=%s model=%s", camera_type, camera_model)
    return {"ok": True}

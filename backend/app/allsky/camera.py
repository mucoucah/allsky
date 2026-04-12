"""Camera detection and first-time setup helpers.

Probes for connected cameras via rpicam/libcamera and provides
the data needed for the setup wizard in the web UI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from .paths import paths

log = logging.getLogger(__name__)


def _lookup_camera_model(sensor: str) -> str:
    """Look up the full camera model name from RPi_cameraInfo.txt.

    The camera info file has lines like:
        camera\timx290\t0\timx290 60.00 fps\t...

    The sensor is in column 2, the model is in column 4.
    allsky.sh expects cameramodel to match column 4.
    """
    p = paths()
    for info_path in (p.config / "RPi_cameraInfo.txt", p.web_config / "RPi_cameraInfo.txt"):
        try:
            if not info_path.exists():
                continue
            for line in info_path.read_text().splitlines():
                if not line.startswith("camera\t"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 4 and parts[1].strip() == sensor:
                    return parts[3].strip()  # e.g. "imx290 60.00 fps"
        except OSError:
            continue
    # Fallback: return sensor name as-is.
    return sensor

# Known camera overlays for /boot/firmware/config.txt (or /boot/config.txt).
# These sensors need a dtoverlay entry to be detected by libcamera.
CAMERA_OVERLAYS: dict[str, dict[str, Any]] = {
    "imx290": {
        "overlay": "dtoverlay=imx290,clock-frequency=74250000",
        "label": "Sony IMX290 (common in allsky cameras)",
    },
    "imx462": {
        "overlay": "dtoverlay=imx290,clock-frequency=74250000",
        "label": "Sony IMX462 (uses imx290 driver)",
    },
    "imx477": {
        "overlay": "dtoverlay=imx477",
        "label": "Sony IMX477 (HQ Camera)",
    },
    "imx708": {
        "overlay": "dtoverlay=imx708",
        "label": "Sony IMX708 (Camera Module 3)",
    },
    "imx219": {
        "overlay": "dtoverlay=imx219",
        "label": "Sony IMX219 (Camera Module 2)",
    },
    "ov5647": {
        "overlay": "dtoverlay=ov5647",
        "label": "OmniVision OV5647 (Camera Module 1)",
    },
    "imx519": {
        "overlay": "dtoverlay=imx519",
        "label": "Sony IMX519 (Arducam 16MP)",
    },
    "arducam_64mp": {
        "overlay": "dtoverlay=arducam-64mp",
        "label": "Arducam 64MP Hawkeye",
    },
}


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

    # Also try v4l2 as fallback for USB cameras (ZWO, etc.).
    # Filter out non-camera devices (codecs, ISPs, decoders).
    _V4L2_IGNORE = {"bcm2835-codec", "bcm2835-isp", "rpi-hevc", "rpivid", "cedrus", "stateless"}
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
                for line in output.splitlines():
                    line = line.strip()
                    if line and not line.startswith("/dev/"):
                        name = line.rstrip(":").strip()
                        # Skip hardware codecs/ISPs — they aren't cameras.
                        if any(skip in name.lower() for skip in _V4L2_IGNORE):
                            continue
                        cameras.append({
                            "index": len(cameras),
                            "model": name,
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

    # Look up the full model name from RPi_cameraInfo.txt.
    # rpicam-hello returns just the sensor name (e.g. "imx290"), but allsky.sh
    # expects the full model string (e.g. "imx290 60.00 fps") from the camera info file.
    if camera_type == "RPi" and camera_model:
        full_model = _lookup_camera_model(camera_model)
        log.info("camera model lookup: sensor=%s -> model=%s", camera_model, full_model)
        camera_model = full_model

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


def _boot_config_path() -> Path | None:
    """Find the boot config.txt path."""
    for p in [Path("/boot/firmware/config.txt"), Path("/boot/config.txt")]:
        if p.exists():
            return p
    return None


def get_camera_overlay_status(sensor: str) -> dict[str, Any]:
    """Check if a camera overlay is already in boot config."""
    info = CAMERA_OVERLAYS.get(sensor.lower())
    if not info:
        return {"known": False, "sensor": sensor}

    cfg = _boot_config_path()
    if not cfg:
        return {"known": True, "sensor": sensor, "overlay": info["overlay"],
                "label": info["label"], "installed": False, "config_found": False}

    try:
        content = cfg.read_text()
        # Check if the overlay line already exists (ignoring comments).
        overlay_key = info["overlay"].split(",")[0]  # e.g. "dtoverlay=imx290"
        installed = any(
            overlay_key in line and not line.strip().startswith("#")
            for line in content.splitlines()
        )
        return {"known": True, "sensor": sensor, "overlay": info["overlay"],
                "label": info["label"], "installed": installed,
                "config_path": str(cfg)}
    except OSError:
        return {"known": True, "sensor": sensor, "overlay": info["overlay"],
                "label": info["label"], "installed": False, "error": "cannot read config"}


async def install_camera_overlay(sensor: str) -> dict[str, Any]:
    """Add the camera dtoverlay to boot config. Returns needs_reboot flag."""
    info = CAMERA_OVERLAYS.get(sensor.lower())
    if not info:
        return {"ok": False, "error": f"Unknown sensor: {sensor}",
                "known_sensors": list(CAMERA_OVERLAYS.keys())}

    status = get_camera_overlay_status(sensor)
    if status.get("installed"):
        return {"ok": True, "already_installed": True, "needs_reboot": False,
                "message": f"Overlay for {sensor} is already in boot config."}

    cfg = _boot_config_path()
    if not cfg:
        return {"ok": False, "error": "Boot config.txt not found"}

    # Write via sudo tee -a.
    overlay_line = f"\n# Allsky camera ({info['label']})\n{info['overlay']}\n"
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "tee", "-a", str(cfg),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=overlay_line.encode()),
            timeout=10,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": f"sudo tee failed: {stderr.decode(errors='replace')}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    log.info("installed camera overlay for %s in %s", sensor, cfg)
    return {"ok": True, "needs_reboot": True, "overlay": info["overlay"],
            "message": f"Added {info['overlay']} to {cfg}. Reboot required."}

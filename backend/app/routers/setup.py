"""First-time setup wizard + camera management endpoints.

These handle initial configuration, camera detection, camera interface
enabling, and service control — so the user never needs a terminal.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.allsky.camera import detect_cameras, setup_initial_config
from app.allsky.service import systemctl
from app.allsky.settings import load_values
from app.allsky.status import read_status

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status")
async def setup_status():
    """Check if initial setup has been completed."""
    settings = load_values()
    status = read_status()
    configured = bool(settings.get("lastchanged"))
    has_camera = bool(settings.get("cameramodel"))

    # Check if allsky service is running.
    try:
        svc = await systemctl("status")
        service_active = svc.get("exit_code") == 0
    except Exception:
        service_active = False

    return {
        "configured": configured,
        "has_camera": has_camera,
        "allsky_status": status.get("status", "Unknown"),
        "camera_type": settings.get("cameratype"),
        "camera_model": settings.get("cameramodel"),
        "service_active": service_active,
    }


@router.get("/detect-cameras")
async def cameras():
    """Detect connected cameras via libcamera/rpicam."""
    return {"cameras": await detect_cameras()}


@router.post("/configure")
async def configure(body: dict[str, Any] = Body(...)):
    """Apply initial camera configuration and optionally start the service."""
    result = await setup_initial_config(
        camera_type=body.get("camera_type", "RPi"),
        camera_model=body.get("camera_model", ""),
        camera_number=body.get("camera_number", 0),
        latitude=body.get("latitude", ""),
        longitude=body.get("longitude", ""),
    )

    # Auto-start the camera service after configuration.
    if body.get("start_capture", True):
        try:
            await systemctl("restart")
            result["service_started"] = True
        except Exception as e:
            result["service_started"] = False
            result["service_error"] = str(e)

    return result


@router.post("/enable-camera")
async def enable_camera():
    """Enable the camera interface via raspi-config non-interactive mode.

    This is the equivalent of raspi-config → Interface Options → Camera → Enable,
    so the user doesn't need to open a terminal.
    """
    # raspi-config nonint: 0 = enable legacy camera, but on Bookworm
    # libcamera doesn't need this. We try both approaches.
    results = []

    # Method 1: dtoverlay in /boot/config.txt (for libcamera on Bookworm).
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "raspi-config", "nonint", "do_camera", "0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        results.append({
            "method": "raspi-config",
            "exit_code": proc.returncode,
            "output": (stdout + stderr).decode(errors="replace").strip(),
        })
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        results.append({"method": "raspi-config", "error": str(e)})

    # Method 2: Ensure camera_auto_detect=1 in config.txt (Bookworm default).
    config_paths = ["/boot/firmware/config.txt", "/boot/config.txt"]
    for cfg_path in config_paths:
        try:
            with open(cfg_path) as f:
                content = f.read()
            if "camera_auto_detect" not in content:
                with open(cfg_path, "a") as f:
                    f.write("\ncamera_auto_detect=1\n")
                results.append({"method": "config.txt", "path": cfg_path, "added": True})
            else:
                results.append({"method": "config.txt", "path": cfg_path, "already_set": True})
            break
        except (FileNotFoundError, PermissionError):
            continue

    needs_reboot = any(r.get("added") for r in results)
    return {
        "results": results,
        "needs_reboot": needs_reboot,
        "message": "Reboot required for camera changes to take effect." if needs_reboot else "Camera interface should already be enabled.",
    }


@router.post("/reboot")
async def reboot():
    """Reboot the Pi. Used after enabling camera interface."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "reboot",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return {"ok": True, "message": "Rebooting... the page will reload in about 60 seconds."}
    except Exception as e:
        raise HTTPException(500, f"Reboot failed: {e}")

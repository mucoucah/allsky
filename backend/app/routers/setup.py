"""First-time setup wizard + camera management endpoints.

These handle initial configuration, camera detection, camera interface
enabling, and service control — so the user never needs a terminal.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException

import httpx

from app.allsky.camera import (
    CAMERA_OVERLAYS, detect_cameras, get_camera_overlay_status,
    install_camera_overlay, setup_initial_config,
)
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
    result = await detect_cameras()
    return {"cameras": result}


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


@router.get("/camera-overlays")
async def camera_overlays():
    """List known camera sensor overlays and their install status."""
    results = {}
    for sensor in CAMERA_OVERLAYS:
        results[sensor] = get_camera_overlay_status(sensor)
    return {"overlays": results}


@router.post("/install-overlay")
async def install_overlay(body: dict[str, Any] = Body(...)):
    """Install a camera dtoverlay in boot config. Requires reboot after."""
    sensor = body.get("sensor", "")
    if not sensor:
        raise HTTPException(400, "sensor field required")
    result = await install_camera_overlay(sensor)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "failed"))
    return result


@router.get("/geocode")
async def geocode(q: str):
    """Look up latitude/longitude from a zip code, city name, or address.

    Uses the free Nominatim (OpenStreetMap) geocoding API.
    """
    if not q or len(q.strip()) < 2:
        raise HTTPException(400, "query too short")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try zip code format first (US zip codes).
            params = {
                "q": q.strip(),
                "format": "json",
                "limit": "1",
                "addressdetails": "1",
            }
            # If it looks like a US zip code, add country hint.
            if q.strip().isdigit() and len(q.strip()) == 5:
                params["countrycodes"] = "us"
                params["postalcode"] = q.strip()
                del params["q"]

            r = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": "allsky-web/1.0"},
            )
            results = r.json()
            if not results:
                return {"found": False, "query": q}

            loc = results[0]
            addr = loc.get("address", {})
            display = loc.get("display_name", "")
            return {
                "found": True,
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "display_name": display,
                "city": addr.get("city") or addr.get("town") or addr.get("village", ""),
                "state": addr.get("state", ""),
                "country": addr.get("country", ""),
            }
    except Exception as e:
        raise HTTPException(500, f"Geocoding failed: {e}")


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
    # We need sudo to write to /boot/config.txt.
    config_paths = ["/boot/firmware/config.txt", "/boot/config.txt"]
    for cfg_path in config_paths:
        try:
            with open(cfg_path) as f:
                content = f.read()
            if "camera_auto_detect" not in content:
                # Use sudo tee -a to append (service user can't write to /boot directly).
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "sudo", "-n", "tee", "-a", cfg_path,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(
                        proc.communicate(input=b"\ncamera_auto_detect=1\n"),
                        timeout=10,
                    )
                    results.append({
                        "method": "config.txt", "path": cfg_path,
                        "added": proc.returncode == 0,
                        "error": None if proc.returncode == 0 else "sudo write failed",
                    })
                except Exception as e:
                    results.append({"method": "config.txt", "path": cfg_path, "error": str(e)})
            else:
                results.append({"method": "config.txt", "path": cfg_path, "already_set": True})
            break
        except FileNotFoundError:
            continue
        except PermissionError:
            results.append({"method": "config.txt", "path": cfg_path, "error": "permission denied reading"})
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

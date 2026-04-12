"""First-time setup wizard endpoints.

These are only used during initial configuration. The setup wizard
guides the user through camera selection, location, and basic settings.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from app.allsky.camera import detect_cameras, setup_initial_config
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
    return {
        "configured": configured,
        "has_camera": has_camera,
        "allsky_status": status.get("status", "Unknown"),
        "camera_type": settings.get("cameratype"),
        "camera_model": settings.get("cameramodel"),
    }


@router.get("/detect-cameras")
async def cameras():
    """Detect connected cameras via libcamera/rpicam."""
    return {"cameras": await detect_cameras()}


@router.post("/configure")
async def configure(body: dict[str, Any] = Body(...)):
    """Apply initial camera configuration."""
    result = await setup_initial_config(
        camera_type=body.get("camera_type", "RPi"),
        camera_model=body.get("camera_model", ""),
        camera_number=body.get("camera_number", 0),
        latitude=body.get("latitude", ""),
        longitude=body.get("longitude", ""),
    )
    return result

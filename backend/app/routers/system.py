"""System status + Allsky service control + Pi power management."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.allsky.service import ServiceError, systemctl
from app.allsky.status import read_camera_info, read_messages, read_status, read_version
from app.allsky.system import allsky_disk_usage, system_snapshot

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("")
async def system_status():
    import logging
    log = logging.getLogger(__name__)
    try:
        host = system_snapshot()
    except Exception as e:
        log.exception("system_snapshot failed")
        host = {"error": str(e)}
    try:
        allsky = {
            "version": read_version(),
            **read_status(),
            "camera": read_camera_info(),
        }
    except Exception as e:
        log.exception("allsky status failed")
        allsky = {"version": "unknown", "status": "Error", "camera": {}, "error": str(e)}
    return {"host": host, "allsky": allsky}


@router.get("/messages")
async def messages(limit: int = 50):
    return read_messages(limit=limit)


@router.get("/allsky-disk")
async def allsky_disk():
    """Disk usage breakdown by Allsky directory (images, darks, videos, etc.)."""
    try:
        return allsky_disk_usage()
    except Exception:
        # Permission errors reading home dir — return zeros.
        return {"images": 0, "darks": 0, "keograms": 0, "startrails": 0,
                "videos": 0, "config": 0, "tmp": 0}


@router.post("/service/{verb}")
async def service_control(verb: str):
    try:
        return await systemctl(verb)
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reboot")
async def reboot_pi():
    """Reboot the Raspberry Pi. Requires sudoers entry for the service user."""
    proc = await asyncio.create_subprocess_exec(
        "sudo", "-n", "/usr/sbin/reboot",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode and proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Reboot failed: {stderr.decode(errors='replace').strip()}"
        )
    return {"ok": True, "message": "Rebooting..."}


@router.post("/shutdown")
async def shutdown_pi():
    """Shutdown the Raspberry Pi. Requires sudoers entry for the service user."""
    proc = await asyncio.create_subprocess_exec(
        "sudo", "-n", "/usr/sbin/shutdown", "-h", "now",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode and proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Shutdown failed: {stderr.decode(errors='replace').strip()}"
        )
    return {"ok": True, "message": "Shutting down..."}

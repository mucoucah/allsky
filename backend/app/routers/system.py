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
    return {
        "host": system_snapshot(),
        "allsky": {
            "version": read_version(),
            **read_status(),
            "camera": read_camera_info(),
        },
    }


@router.get("/messages")
async def messages(limit: int = 50):
    return read_messages(limit=limit)


@router.get("/allsky-disk")
async def allsky_disk():
    """Disk usage breakdown by Allsky directory (images, darks, videos, etc.)."""
    return allsky_disk_usage()


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

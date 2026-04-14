"""System status + Allsky service control + Pi power management."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from app.allsky.service import ServiceError, systemctl
from app.allsky.status import read_camera_info, read_messages, read_status, read_version
from app.allsky.system import allsky_disk_usage, system_snapshot

router = APIRouter(prefix="/api/system", tags=["system"])

# In-memory throttle event history (capped, per-process).
# Each entry: {ts, types[], cpu_temp_c, cpu_percent, activity}
_throttle_history: list[dict[str, Any]] = []
_last_throttle_flags: dict[str, bool] = {}
_MAX_HISTORY = 50


async def _current_activity() -> str:
    """Best-effort detection of what the Pi is doing right now.

    Looks at recent journalctl messages from allsky.service for keywords.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", "allsky", "--no-pager", "-n", "20",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        text = stdout.decode(errors="replace")
        if "timelapse" in text.lower():
            return "Generating timelapse"
        if "keogram" in text.lower():
            return "Generating keogram"
        if "startrail" in text.lower():
            return "Generating startrails"
        if "upload" in text.lower():
            return "Uploading images"
        if "saving" in text.lower() or "got image" in text.lower():
            return "Capturing image"
        if "starting exposure" in text.lower():
            return "Exposing (long exposure)"
    except Exception:
        pass
    return "Normal operation"


def _record_throttle_event(host: dict[str, Any], activity: str) -> None:
    """If a NEW throttle condition has appeared since last check, log it."""
    t = host.get("throttle")
    if not t:
        return
    cur = {
        "under_voltage": bool(t.get("under_voltage_now")),
        "freq_capped": bool(t.get("freq_capped_now")),
        "throttled": bool(t.get("throttled_now")),
        "soft_temp_limit": bool(t.get("soft_temp_limit_now")),
    }
    # Find newly-triggered flags (not active last time, now active).
    newly_active = [k for k, v in cur.items()
                    if v and not _last_throttle_flags.get(k, False)]
    _last_throttle_flags.update(cur)
    if newly_active:
        _throttle_history.append({
            "ts": int(time.time()),
            "types": newly_active,
            "cpu_temp_c": host.get("cpu_temp_c"),
            "cpu_percent": host.get("cpu_percent"),
            "activity": activity,
        })
        # Cap history.
        if len(_throttle_history) > _MAX_HISTORY:
            _throttle_history[:] = _throttle_history[-_MAX_HISTORY:]


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

    # Record throttle events with activity context.
    activity = await _current_activity()
    try:
        _record_throttle_event(host, activity)
    except Exception:
        log.exception("throttle record failed")
    host["current_activity"] = activity

    # Override status with actual systemd service state — status.json is often stale.
    try:
        svc = await systemctl("status")
        stdout = svc.get("stdout", "")
        if "active (running)" in stdout.lower():
            allsky["status"] = "Running"
            allsky["service_active"] = True
        elif "inactive" in stdout.lower() or "dead" in stdout.lower():
            allsky["service_active"] = False
            if allsky["status"] in ("Not configured", "Unknown"):
                allsky["status"] = "Stopped"
        elif "failed" in stdout.lower():
            allsky["status"] = "Error"
            allsky["service_active"] = False
        else:
            allsky["service_active"] = False
    except Exception:
        allsky["service_active"] = False

    return {"host": host, "allsky": allsky}


@router.get("/throttle-history")
async def throttle_history():
    """Return the in-memory history of throttle events with context."""
    return {"events": list(reversed(_throttle_history))}


@router.post("/throttle-history/clear")
async def clear_throttle_history():
    """Clear the throttle event history."""
    _throttle_history.clear()
    _last_throttle_flags.clear()
    return {"ok": True, "cleared": True}


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

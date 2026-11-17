"""Dark-frame list, file, delete, and capture. URLs stay under /api/maintenance."""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.allsky.paths import paths
from app.allsky.settings import load_values, save_values

log = logging.getLogger(__name__)
router = APIRouter()

@router.get("/darks")
async def list_darks():
    """List captured dark frames."""
    darks_dir = paths().darks
    out: list[dict] = []
    try:
        if not darks_dir.exists():
            return {"darks": [], "darks_dir": str(darks_dir), "total_bytes": 0}
    except OSError:
        return {"darks": [], "darks_dir": str(darks_dir), "total_bytes": 0}

    total_bytes = 0
    try:
        for p in sorted(darks_dir.iterdir(), reverse=True):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".raw"}:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            # Try to extract temperature from filename (e.g. "20.jpg", "-5.jpg").
            temp_match = re.match(r"^(-?\d+(?:\.\d+)?)\.", p.name)
            temp = float(temp_match.group(1)) if temp_match else None
            out.append({
                "name": p.name,
                "size_bytes": st.st_size,
                "mtime": int(st.st_mtime),
                "temperature_c": temp,
            })
            total_bytes += st.st_size
    except OSError as e:
        log.warning("list_darks: %s", e)

    return {"darks": out, "darks_dir": str(darks_dir), "total_bytes": total_bytes}


@router.get("/darks/{name}")
async def get_dark(name: str):
    """Serve a dark frame file."""
    if "/" in name or ".." in name:
        raise HTTPException(400, "invalid name")
    p = paths().darks / name
    if not p.exists():
        raise HTTPException(404, "not found")
    return FileResponse(str(p))


@router.delete("/darks/{name}")
async def delete_dark(name: str):
    """Delete a dark frame file."""
    if "/" in name or ".." in name:
        raise HTTPException(400, "invalid name")
    p = paths().darks / name
    if not p.exists():
        raise HTTPException(404, "not found")
    try:
        p.unlink()
    except OSError as e:
        raise HTTPException(500, f"delete failed: {e}")
    return {"deleted": name}


@router.post("/darks/capture")
async def capture_dark():
    """Enable dark frame capture mode and restart the service."""
    values = load_values()
    values["takedarkframes"] = "true"
    values["lastchanged"] = "1"
    save_values(values)

    # Restart the camera service so it picks up dark capture mode.
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "/usr/bin/systemctl", "restart", "allsky.service",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "message": "Dark frame capture enabled. The camera will capture darks. "
                   "Turn off 'takedarkframes' in Settings when done.",
    }

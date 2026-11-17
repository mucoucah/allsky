"""Regenerate a past night. URLs stay under /api/maintenance/generate."""
from __future__ import annotations

import asyncio
import os
import re

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths

router = APIRouter()

@router.get("/generate/dates")
async def available_dates():
    """List dates with images available for regeneration."""
    images_dir = paths().images
    dates: list[str] = []
    try:
        if images_dir.exists():
            for p in sorted(images_dir.iterdir(), reverse=True):
                if p.is_dir() and re.match(r"^\d{8}$", p.name):
                    # Count images in the directory.
                    try:
                        count = sum(1 for f in p.iterdir() if f.is_file() and
                                    f.suffix.lower() in {".jpg", ".jpeg", ".png"})
                        dates.append({"date": p.name, "image_count": count})
                    except OSError:
                        pass
    except OSError:
        pass
    return {"dates": dates}


@router.post("/generate/{date}")
async def generate_for_date(date: str, body: dict = Body(...)):
    """Regenerate keogram, startrail, or timelapse for a given date (YYYYMMDD)."""
    if not re.match(r"^\d{8}$", date):
        raise HTTPException(400, "date must be YYYYMMDD")

    kinds = body.get("kinds", ["keogram", "startrails", "timelapse"])
    if isinstance(kinds, str):
        kinds = [kinds]

    script = paths().scripts / "generateForDay.sh"
    if not script.exists():
        raise HTTPException(500, "generateForDay.sh not found")

    # Build args.
    args = ["bash", str(script)]
    if "keogram" in kinds:
        args.append("--keogram")
    if "startrails" in kinds:
        args.append("--startrails")
    if "timelapse" in kinds:
        args.append("--timelapse")
    args.append(date)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ALLSKY_HOME": str(paths().home)},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1800)  # 30 min
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "kinds": kinds,
            "date": date,
            "output": (stdout + stderr).decode(errors="replace")[-4000:],
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Generation timed out after 30 minutes"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

"""Meteor watcher config and the read-only hit archive.

URLs stay under /api/notifications. Hits are the JSON sidecars the processor
writes at html/allsky/meteors/<date>/*.json, plus the JPEG frame and crop
beside each file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from app.allsky.paths import paths
from app.notify.meteor import detect as detect_meteor
from app.notify.store import load_comet_config, save_comet_config

router = APIRouter()

_DATE = re.compile(r"^\d{8}$")
_IMAGE = re.compile(r"^meteor_[A-Za-z0-9._-]+\.(?:jpg|jpeg|png)$", re.IGNORECASE)

@router.get("/meteor/config")
async def get_meteor_config():
    return load_comet_config()


@router.put("/meteor/config")
async def set_meteor_config(body: dict = Body(...)):
    save_comet_config(body)
    return {"ok": True}


@router.post("/meteor/detect-now")
async def run_meteor_now():
    """Run meteor detection on the current frame and return the result.
    Does NOT dispatch alerts — for testing / preview only."""
    target = paths().latest_image
    if not target.exists():
        raise HTTPException(404, "no current frame")
    cfg = load_comet_config()
    result = detect_meteor(
        target, min_length=cfg.get("min_streak_length", 100), annotate=False,
    )
    return {
        "meteor_count": result.meteor_count,
        "line_count": result.line_count,
        "lines": result.lines,
    }


def meteor_roots() -> list[Path]:
    """Directories that hold html/allsky/meteors/<date>/*.json."""
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            return
        seen.add(key)
        roots.append(path)

    add(paths().html / "allsky" / "meteors")
    try:
        from app.routers.offload import _load
        cfg, _payload = _load()
        data = getattr(cfg.processor, "data_dir", "") or ""
        if data:
            add(Path(data) / "html" / "allsky" / "meteors")
    except Exception:
        pass
    return roots


def _hit_file(root: Path, date: str, name: str) -> Path | None:
    candidate = (root / date / name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


@router.get("/meteor/hits")
async def list_meteor_hits(limit: int = Query(200, ge=1, le=1000)):
    """Read-only list of saved meteor hits, newest first."""
    found: list[dict] = []
    seen: set[str] = set()
    for root in meteor_roots():
        if not root.is_dir():
            continue
        try:
            files = list(root.glob("*/*.json"))
        except OSError:
            continue
        for path in files:
            date = path.parent.name
            if not _DATE.match(date):
                continue
            key = f"{date}/{path.name}"
            if key in seen:
                continue
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            seen.add(key)

            def image_name(value: object) -> str | None:
                if not isinstance(value, str) or not value:
                    return None
                base = Path(value).name
                if not _IMAGE.match(base):
                    return None
                return base

            frame = image_name(payload.get("frame"))
            crop = image_name(payload.get("crop"))

            def url(name: str | None) -> str | None:
                if not name:
                    return None
                return f"/api/notifications/meteor/hits/file?date={date}&name={name}"

            found.append({
                "date": date,
                "id": path.stem,
                "time": payload.get("time"),
                "meteor_count": payload.get("meteor_count"),
                "lines": payload.get("lines") or [],
                "frame": frame,
                "crop": crop,
                "crop_url": url(crop) or url(frame),
                "frame_url": url(frame),
            })
    found.sort(key=lambda hit: (str(hit.get("time") or ""), str(hit["id"])), reverse=True)
    return {"hits": found[:limit], "total": len(found)}


@router.get("/meteor/hits/file")
async def meteor_hit_file(date: str = Query(...), name: str = Query(...)):
    """Serve one hit JPEG (full frame or crop) from the meteor archive."""
    if not _DATE.match(date) or not _IMAGE.match(name) or "/" in name or ".." in name:
        raise HTTPException(400, "invalid hit file")
    for root in meteor_roots():
        candidate = _hit_file(root, date, name)
        if candidate is not None and candidate.is_file():
            media = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            return FileResponse(candidate, media_type=media)
    raise HTTPException(404, "not found")

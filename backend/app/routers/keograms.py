"""Keogram + startrails + timelapse video listing & file serving."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.allsky.paths import paths

router = APIRouter(prefix="/api/keograms", tags=["keograms"])

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".webm", ".mov"}


def _list_dir(d: Path, extensions: set[str] = _IMAGE_EXTS) -> list[dict]:
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir(), reverse=True):
        if not p.is_file():
            continue
        if p.suffix.lower() not in extensions:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        out.append(
            {"name": p.name, "size_bytes": st.st_size, "mtime": int(st.st_mtime)}
        )
    return out


# ── Keograms ────────────────────────────────────────────────────

@router.get("/keograms")
async def keograms():
    return {"items": _list_dir(paths().keograms_dir)}


@router.get("/keograms/{name}")
async def keogram_file(name: str):
    p = paths().keograms_dir / name
    if not p.exists() or ".." in name or "/" in name:
        raise HTTPException(404, "not found")
    return FileResponse(p)


# ── Startrails ──────────────────────────────────────────────────

@router.get("/startrails")
async def startrails():
    return {"items": _list_dir(paths().startrails_dir)}


@router.get("/startrails/{name}")
async def startrail_file(name: str):
    p = paths().startrails_dir / name
    if not p.exists() or ".." in name or "/" in name:
        raise HTTPException(404, "not found")
    return FileResponse(p)


# ── Timelapse Videos ────────────────────────────────────────────

def _extract_date(name: str) -> str | None:
    """Try to pull a YYYYMMDD or YYYY-MM-DD date from a filename."""
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


@router.get("/videos")
async def videos(
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    sort: str = Query("date", description="Sort by: date, name, size"),
    order: str = Query("desc", description="Sort order: asc or desc"),
):
    items = _list_dir(paths().videos_dir, extensions=_VIDEO_EXTS)

    # Enrich with extracted date
    for item in items:
        item["date"] = _extract_date(item["name"])

    # Filter by date if specified
    if date:
        items = [i for i in items if i["date"] == date]

    # Sort
    reverse = order.lower() != "asc"
    if sort == "name":
        items.sort(key=lambda i: i["name"].lower(), reverse=reverse)
    elif sort == "size":
        items.sort(key=lambda i: i["size_bytes"], reverse=reverse)
    else:  # date (default) — use mtime
        items.sort(key=lambda i: i["mtime"], reverse=reverse)

    # Collect unique dates for the date picker
    all_items = _list_dir(paths().videos_dir, extensions=_VIDEO_EXTS)
    dates = sorted(
        {_extract_date(i["name"]) for i in all_items if _extract_date(i["name"])},
        reverse=True,
    )

    return {"items": items, "dates": dates, "total": len(items)}


@router.get("/videos/{name}")
async def video_file(name: str):
    p = paths().videos_dir / name
    if not p.exists() or ".." in name or "/" in name:
        raise HTTPException(404, "not found")
    return FileResponse(p, media_type="video/mp4")

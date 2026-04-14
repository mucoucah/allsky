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
    try:
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
    except OSError:
        pass
    return out


def _aggregate_per_day_subdir(subdir: str, extensions: set[str] = _IMAGE_EXTS) -> list[dict]:
    """Aggregate files from all per-day directories: images/YYYYMMDD/{subdir}/*.

    Also includes files from html/allsky/{subdir}/ (legacy Allsky layout).
    """
    out: list[dict] = []
    seen_paths: set[str] = set()

    # Per-day directories: images/YYYYMMDD/{subdir}/
    try:
        images_root = paths().images
        if images_root.exists():
            for date_dir in sorted(images_root.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                if not re.match(r"^\d{8}$", date_dir.name):
                    continue
                sub = date_dir / subdir
                if not sub.exists():
                    continue
                try:
                    for p in sorted(sub.iterdir(), reverse=True):
                        if not p.is_file():
                            continue
                        if p.suffix.lower() not in extensions:
                            continue
                        full = str(p)
                        if full in seen_paths:
                            continue
                        seen_paths.add(full)
                        try:
                            st = p.stat()
                        except OSError:
                            continue
                        out.append({
                            "name": p.name,
                            "size_bytes": st.st_size,
                            "mtime": int(st.st_mtime),
                            "date_dir": date_dir.name,  # so we can serve from right dir
                        })
                except OSError:
                    continue
    except OSError:
        pass

    # Fallback: html/allsky/{subdir}/ (legacy)
    legacy_dir = getattr(paths(), f"{subdir}_dir", None)
    if legacy_dir is None:
        # keograms/startrails/videos
        legacy_dir = paths().html / "allsky" / subdir
    try:
        if legacy_dir.exists():
            for p in sorted(legacy_dir.iterdir(), reverse=True):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in extensions:
                    continue
                full = str(p)
                if full in seen_paths:
                    continue
                seen_paths.add(full)
                try:
                    st = p.stat()
                except OSError:
                    continue
                out.append({
                    "name": p.name,
                    "size_bytes": st.st_size,
                    "mtime": int(st.st_mtime),
                })
    except OSError:
        pass

    # Sort all by mtime desc.
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _find_file(subdir: str, name: str) -> Path | None:
    """Locate a file by name in any of the expected locations."""
    if "/" in name or ".." in name:
        return None
    # Try per-day dirs.
    try:
        images_root = paths().images
        if images_root.exists():
            for date_dir in images_root.iterdir():
                if not date_dir.is_dir():
                    continue
                candidate = date_dir / subdir / name
                if candidate.is_file():
                    return candidate
    except OSError:
        pass
    # Fallback: html/allsky/{subdir}/{name}
    try:
        legacy = paths().html / "allsky" / subdir / name
        if legacy.is_file():
            return legacy
    except OSError:
        pass
    return None


# ── Keograms ────────────────────────────────────────────────────

@router.get("/keograms")
async def keograms():
    return {"items": _aggregate_per_day_subdir("keograms")}


@router.get("/keograms/{name}")
async def keogram_file(name: str):
    p = _find_file("keograms", name)
    if not p:
        raise HTTPException(404, "not found")
    return FileResponse(p)


# ── Startrails ──────────────────────────────────────────────────

@router.get("/startrails")
async def startrails():
    return {"items": _aggregate_per_day_subdir("startrails")}


@router.get("/startrails/{name}")
async def startrail_file(name: str):
    p = _find_file("startrails", name)
    if not p:
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
    items = _aggregate_per_day_subdir("videos", extensions=_VIDEO_EXTS)

    # Enrich with extracted date
    for item in items:
        item["date"] = item.get("date_dir") and (
            item["date_dir"][:4] + "-" + item["date_dir"][4:6] + "-" + item["date_dir"][6:8]
        ) or _extract_date(item["name"])

    # Filter by date if specified
    if date:
        items = [i for i in items if i.get("date") == date]

    # Sort
    reverse = order.lower() != "asc"
    if sort == "name":
        items.sort(key=lambda i: i["name"].lower(), reverse=reverse)
    elif sort == "size":
        items.sort(key=lambda i: i["size_bytes"], reverse=reverse)
    else:  # date (default) — use mtime
        items.sort(key=lambda i: i["mtime"], reverse=reverse)

    # Collect unique dates for the date picker
    all_items = _aggregate_per_day_subdir("videos", extensions=_VIDEO_EXTS)
    dates_set: set[str] = set()
    for i in all_items:
        d = i.get("date_dir")
        if d:
            dates_set.add(d[:4] + "-" + d[4:6] + "-" + d[6:8])
        else:
            ext = _extract_date(i["name"])
            if ext:
                dates_set.add(ext)

    return {"items": items, "dates": sorted(dates_set, reverse=True), "total": len(items)}


@router.get("/videos/{name}")
async def video_file(name: str):
    p = _find_file("videos", name)
    if not p:
        raise HTTPException(404, "not found")
    return FileResponse(p, media_type="video/mp4")

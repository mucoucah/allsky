"""Image gallery: list days, list images per day, serve files & thumbnails.

The DB-backed index is built/refreshed on demand for any date that hasn't been
indexed yet. For a typical Pi capture cadence (~5 s) a single night is ~5–10k
images, so on first scan we tradeoff a few seconds of EXIF I/O for instant
filtering afterwards.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.allsky.images import (
    list_date_dirs,
    resolve_image,
    scan_to_records,
    thumbnail_for,
)
from app.db import connect, upsert_image

router = APIRouter(prefix="/api/images", tags=["images"])


@router.get("/days")
async def days():
    return {"dates": list_date_dirs()}


@router.get("")
async def images(
    date: str = Query(..., description="YYYYMMDD date directory"),
    sort: str = Query("captured_at"),
    order: str = Query("desc"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    if sort not in {"captured_at", "filename", "size_bytes", "exposure_us", "iso"}:
        raise HTTPException(400, "invalid sort field")
    if order not in {"asc", "desc"}:
        raise HTTPException(400, "order must be asc or desc")

    await _ensure_indexed(date)

    async with connect() as conn:
        cur = await conn.execute(
            f"SELECT * FROM images_meta WHERE date_dir=? ORDER BY {sort} {order.upper()} LIMIT ? OFFSET ?",
            (date, limit, offset),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM images_meta WHERE date_dir=?", (date,)
        )
        total = (await cur.fetchone())["n"]

    return {"date": date, "total": total, "items": rows}


@router.get("/file")
async def get_file(path: str = Query(...)):
    p = resolve_image(path)
    if not p:
        raise HTTPException(404, "not found")
    return FileResponse(p)


@router.get("/thumb")
async def get_thumb(path: str = Query(...)):
    p = resolve_image(path)
    if not p:
        raise HTTPException(404, "not found")
    t = thumbnail_for(p)
    return FileResponse(t or p)


async def _ensure_indexed(date: str) -> None:
    """Index a date dir if it hasn't been seen yet, or if its newest mtime is
    newer than what we have stored. Cheap to call on every list request."""
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT MAX(captured_at) AS m, COUNT(*) AS n FROM images_meta WHERE date_dir=?",
            (date,),
        )
        row = await cur.fetchone()
    have_count = row["n"] if row else 0

    # Quick decision: if we have nothing, do a full scan; otherwise scan and
    # upsert (sqlite ON CONFLICT keeps the cost low).
    if have_count == 0:
        await _full_scan(date)
        return

    # Incremental: only re-scan if the directory has been modified.
    from app.allsky.paths import paths
    d = paths().day_dir(date)
    if not d.exists():
        return
    try:
        if d.stat().st_mtime > (row["m"] or 0):
            await _full_scan(date)
    except OSError:
        pass


async def _full_scan(date: str) -> None:
    async with connect() as conn:
        for rec in scan_to_records(date):
            await upsert_image(conn, rec)
        await conn.commit()

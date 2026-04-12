"""Keogram + startrails listing & file serving."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.allsky.paths import paths

router = APIRouter(prefix="/api/keograms", tags=["keograms"])


def _list_dir(d: Path) -> list[dict]:
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir(), reverse=True):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        out.append(
            {"name": p.name, "size_bytes": st.st_size, "mtime": int(st.st_mtime)}
        )
    return out


@router.get("/keograms")
async def keograms():
    return {"items": _list_dir(paths().keograms_dir)}


@router.get("/startrails")
async def startrails():
    return {"items": _list_dir(paths().startrails_dir)}


@router.get("/keograms/{name}")
async def keogram_file(name: str):
    p = paths().keograms_dir / name
    if not p.exists() or ".." in name or "/" in name:
        raise HTTPException(404, "not found")
    return FileResponse(p)


@router.get("/startrails/{name}")
async def startrail_file(name: str):
    p = paths().startrails_dir / name
    if not p.exists() or ".." in name or "/" in name:
        raise HTTPException(404, "not found")
    return FileResponse(p)

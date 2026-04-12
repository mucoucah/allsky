"""Mask CRUD: list, fetch PNG, upload PNG, delete."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.allsky.masks import (
    delete_mask,
    latest_image_dimensions,
    list_masks,
    read_mask,
    write_mask,
)

router = APIRouter(prefix="/api/masks", tags=["masks"])


@router.get("")
async def index():
    dims = latest_image_dimensions()
    return {
        "masks": list_masks(),
        "frame_dimensions": {"width": dims[0], "height": dims[1]} if dims else None,
    }


@router.get("/{name}")
async def get(name: str):
    p = read_mask(name)
    if not p:
        raise HTTPException(404, "mask not found")
    return FileResponse(p, media_type="image/png")


@router.put("/{name}")
async def put(name: str, body: bytes = Body(..., media_type="image/png")):
    try:
        meta = write_mask(name, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return JSONResponse(meta)


@router.delete("/{name}")
async def delete(name: str):
    if not delete_mask(name):
        raise HTTPException(404, "mask not found")
    return {"deleted": name}

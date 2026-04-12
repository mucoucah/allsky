"""Settings: schema, current values, validated patch."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.allsky.service import ServiceError, apply_settings
from app.allsky.settings import grouped_schema, load_values, validate_patch
from app.db import log_setting_change

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/schema")
async def schema():
    return grouped_schema()


@router.get("")
async def values():
    return load_values()


@router.patch("")
async def patch(req: Request, body: dict[str, Any] = Body(...)):
    errors = validate_patch(body)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    current = load_values()
    actor = req.session.get("user") if hasattr(req, "session") else None
    for k, v in body.items():
        await log_setting_change(actor, k, current.get(k), v)

    try:
        result = await apply_settings(body)
    except ServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result)

    return {"ok": True, "applied": list(body.keys()), "result": result}

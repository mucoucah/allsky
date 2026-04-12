"""Settings: schema, current values, validated patch."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.allsky.service import ServiceError, apply_settings
from app.allsky.settings import grouped_schema, load_values, validate_patch
from app.allsky.paths import paths
from app.db import connect, log_setting_change

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/schema")
async def schema():
    try:
        result = grouped_schema()
        p = paths().options_file
        log.info("schema: options_file=%s exists=%s tabs=%d", p, p.exists(), len(result))
        return result
    except Exception as e:
        log.exception("schema endpoint failed")
        raise HTTPException(500, detail=f"Failed to load schema: {e}")


@router.get("")
async def values():
    try:
        return load_values()
    except Exception as e:
        log.exception("values endpoint failed")
        raise HTTPException(500, detail=f"Failed to load settings: {e}")


@router.get("/debug")
async def debug():
    """Debug endpoint — shows what the backend sees for settings files."""
    p = paths()
    import json
    import os

    def _file_info(path):
        info = {"path": str(path), "exists": path.exists()}
        if path.exists():
            try:
                st = path.stat()
                info["size"] = st.st_size
                info["uid"] = st.st_uid
                info["gid"] = st.st_gid
                info["mode"] = oct(st.st_mode)
            except OSError as e:
                info["stat_error"] = str(e)
            try:
                path.open("r").close()
                info["readable"] = True
            except OSError as e:
                info["readable"] = False
                info["read_error"] = str(e)
        return info

    result = {
        "allsky_home": str(p.home),
        "web_config_dir": str(p.web_config),
        "running_as_user": os.getenv("USER", "unknown"),
        "running_as_uid": os.getuid(),
        "options_file": _file_info(p.options_file),
        "settings_file": _file_info(p.settings_file),
        "allsky_home_options": _file_info(p.config / "options.json"),
        "allsky_home_settings": _file_info(p.config / "settings.json"),
    }
    if p.options_file.exists():
        try:
            with p.options_file.open() as f:
                raw = json.load(f)
            result["options_type"] = type(raw).__name__
            result["options_len"] = len(raw) if isinstance(raw, list) else "n/a"
        except Exception as e:
            result["options_error"] = str(e)
    if p.settings_file.exists():
        try:
            with p.settings_file.open() as f:
                result["settings_keys"] = list(json.load(f).keys())
        except Exception as e:
            result["settings_error"] = str(e)
    return result


@router.get("/audit")
async def audit(limit: int = 50):
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT * FROM settings_audit ORDER BY ts DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cur.fetchall()]


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

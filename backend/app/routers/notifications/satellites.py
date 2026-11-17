"""Satellite watcher config. URLs stay under /api/notifications."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.notify.store import load_sat_config, save_sat_config

router = APIRouter()

@router.get("/satellites/config")
async def get_sat_config():
    return load_sat_config()


@router.put("/satellites/config")
async def set_sat_cfg(body: dict = Body(...)):
    cfg = load_sat_config()
    cfg.update(body)
    save_sat_config(cfg)
    return {"ok": True}


@router.get("/satellites/passes")
async def sat_passes():
    from app.notify.watchers import get_sat_cache
    return get_sat_cache()


@router.post("/satellites/scan-now")
async def sat_scan_now():
    from app.notify.watchers import _get_camera_latlon, set_sat_cache
    from app.notify.satellites import compute_passes, current_positions, download_tles
    latlon = _get_camera_latlon()
    if latlon is None:
        raise HTTPException(400, "Camera latitude/longitude not configured")
    lat, lon = latlon
    cfg = load_sat_config()
    groups = cfg.get("tle_groups", ["stations", "visual"])
    tles = await download_tles(groups)
    passes = compute_passes(
        lat, lon, 0, tles,
        hours_ahead=cfg.get("hours_ahead", 24),
        min_elevation_deg=cfg.get("min_elevation_deg", 10),
    )
    overhead = current_positions(lat, lon, 0, tles)
    import time as _time
    result = {
        "passes": [p.to_dict() for p in passes[:50]],
        "overhead": [s.to_dict() for s in overhead],
        "timestamp": _time.time(),
    }
    set_sat_cache(result)
    return result

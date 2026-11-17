"""ADS-B watcher config. URLs stay under /api/notifications."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.notify.adsb import fetch_nearby
from app.notify.store import load_adsb_config, save_adsb_config

router = APIRouter()

@router.get("/adsb/config")
async def get_adsb_config():
    cfg = load_adsb_config()
    if cfg.get("opensky_password"):
        cfg["opensky_password"] = "****"
    return cfg


@router.put("/adsb/config")
async def set_adsb_config(body: dict = Body(...)):
    cfg = load_adsb_config()
    if body.get("opensky_password") == "****":
        body["opensky_password"] = cfg.get("opensky_password", "")
    cfg.update(body)
    save_adsb_config(cfg)
    return {"ok": True}


@router.get("/adsb/nearby")
async def adsb_nearby():
    from app.notify.watchers import get_adsb_cache
    cache = get_adsb_cache()
    return cache


@router.post("/adsb/scan-now")
async def adsb_scan_now():
    from app.notify.watchers import _get_camera_latlon, set_adsb_cache
    latlon = _get_camera_latlon()
    if latlon is None:
        raise HTTPException(400, "Camera latitude/longitude not configured")
    lat, lon = latlon
    cfg = load_adsb_config()
    aircraft = await fetch_nearby(
        lat, lon,
        radius_km=cfg.get("radius_km", 50),
        min_altitude_m=cfg.get("min_altitude_m", 0),
        username=cfg.get("opensky_username", ""),
        password=cfg.get("opensky_password", ""),
    )
    result = {
        "aircraft": [ac.to_dict() for ac in aircraft],
        "timestamp": __import__("time").time(),
        "count": len(aircraft),
    }
    set_adsb_cache(result)
    return result

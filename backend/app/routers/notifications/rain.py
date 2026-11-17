"""Rain watcher config. URLs stay under /api/notifications."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths
from app.notify.rain import detect_rain
from app.notify.store import load_rain_config, save_rain_config

router = APIRouter()

@router.get("/rain/config")
async def get_rain_config():
    return load_rain_config()


@router.put("/rain/config")
async def set_rain_config(body: dict = Body(...)):
    cfg = load_rain_config()
    cfg.update(body)
    save_rain_config(cfg)
    return {"ok": True}


@router.post("/rain/detect-now")
async def rain_detect_now():
    """Run rain detection on the current frame."""
    try:
        target = paths().latest_image
        if not target.exists():
            raise HTTPException(404, "no current frame")
    except OSError:
        raise HTTPException(404, "no current frame")

    mask_path = paths().masks_dir / "mask.png"
    cfg = load_rain_config()
    result = detect_rain(
        target,
        mask_path=mask_path if mask_path.exists() else None,
        confidence_threshold=cfg.get("confidence_threshold", 0.4),
    )
    return {
        "rain_detected": result.rain_detected,
        "confidence": result.confidence,
        "droplet_count": result.droplet_count,
        "contrast_score": result.contrast_score,
        "message": result.message,
    }

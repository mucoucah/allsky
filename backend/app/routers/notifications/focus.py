"""Focus watcher config. URLs stay under /api/notifications."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths
from app.notify.focus import assess_focus, sharpness_score
from app.notify.store import load_focus_config, save_focus_config

router = APIRouter()

async def get_focus_config():
    return load_focus_config()


@router.put("/focus/config")
async def set_focus_config(body: dict = Body(...)):
    save_focus_config(body)
    return {"ok": True}


@router.post("/focus/calibrate")
async def calibrate_focus():
    """Take the current frame's sharpness score as the baseline."""
    target = paths().latest_image
    if not target.exists():
        raise HTTPException(404, "no current frame")
    score = sharpness_score(target)
    if score is None:
        raise HTTPException(500, "could not compute sharpness")
    cfg = load_focus_config()
    cfg["baseline_sharpness"] = round(score, 2)
    save_focus_config(cfg)
    return {"ok": True, "baseline_sharpness": cfg["baseline_sharpness"]}


@router.get("/focus/current")
async def current_focus():
    """Get the current sharpness assessment."""
    try:
        target = paths().latest_image
        if not target.exists():
            return {"score": None, "baseline": None, "threshold": None, "status": "no frame"}
    except OSError:
        return {"score": None, "baseline": None, "threshold": None, "status": "no frame"}
    cfg = load_focus_config()
    try:
        result = assess_focus(
            target, cfg.get("baseline_sharpness"), cfg.get("threshold_pct", 60)
        )
        return result
    except OSError:
        return {"score": None, "baseline": None, "threshold": None, "status": "permission denied"}

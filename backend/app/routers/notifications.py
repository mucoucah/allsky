"""Notification config + manual send + watcher config + test endpoints."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths
from app.notify.channels import Attachment, dispatch
from app.notify.focus import assess_focus, sharpness_score
from app.notify.meteor import detect as detect_meteor
from app.notify.store import (
    delete_channel,
    load_channels,
    load_comet_config,
    load_focus_config,
    redacted_channels,
    save_comet_config,
    save_focus_config,
    upsert_channel,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# ── channels ─────────────────────────────────────────────────────


@router.get("/channels")
async def list_channels():
    return {"channels": redacted_channels()}


@router.post("/channels")
async def create_channel(body: dict = Body(...)):
    body.setdefault("id", str(uuid.uuid4())[:8])
    return upsert_channel(body)


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: str, body: dict = Body(...)):
    body["id"] = channel_id
    return upsert_channel(body)


@router.delete("/channels/{channel_id}")
async def remove_channel(channel_id: str):
    if not delete_channel(channel_id):
        raise HTTPException(404, "channel not found")
    return {"deleted": channel_id}


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: str):
    channels = load_channels()
    ch = next((c for c in channels if c["id"] == channel_id), None)
    if not ch:
        raise HTTPException(404, "channel not found")

    # Build a test attachment (snapshot).
    atts: list[Attachment] = []
    p = paths().latest_image
    if p.exists():
        try:
            atts.append(Attachment("test_snapshot.jpg", p.read_bytes(), "image/jpeg"))
        except OSError:
            pass

    results = await dispatch(
        [ch],
        subject="Allsky-web test notification",
        body="If you see this, the channel is configured correctly.",
        attachments=atts,
    )
    ok = results.get(ch["id"], False)
    if not ok:
        raise HTTPException(500, "send failed — check backend logs for details")
    return {"ok": True}


@router.post("/send")
async def manual_send(body: dict = Body(...)):
    """Manual send: user writes a subject/body and chooses attachments."""
    subject = body.get("subject", "Allsky notification")
    text = body.get("body", "")
    include_snapshot = body.get("include_snapshot", True)
    include_timelapse = body.get("include_timelapse", False)

    atts: list[Attachment] = []
    if include_snapshot:
        p = paths().latest_image
        if p.exists():
            try:
                atts.append(Attachment("snapshot.jpg", p.read_bytes(), "image/jpeg"))
            except OSError:
                pass
    if include_timelapse:
        tl = paths().tmp / "mini-timelapse.mp4"
        if tl.exists():
            try:
                atts.append(Attachment("timelapse.mp4", tl.read_bytes(), "video/mp4"))
            except OSError:
                pass

    channels = load_channels()
    results = await dispatch(channels, subject, text, atts)
    return {"results": results}


# ── meteor config ────────────────────────────────────────────────


@router.get("/meteor/config")
async def get_meteor_config():
    return load_comet_config()


@router.put("/meteor/config")
async def set_meteor_config(body: dict = Body(...)):
    save_comet_config(body)
    return {"ok": True}


@router.post("/meteor/detect-now")
async def run_meteor_now():
    """Run meteor detection on the current frame and return the result.
    Does NOT dispatch alerts — for testing / preview only."""
    target = paths().latest_image
    if not target.exists():
        raise HTTPException(404, "no current frame")
    cfg = load_comet_config()
    result = detect_meteor(
        target, min_length=cfg.get("min_streak_length", 100), annotate=False,
    )
    return {
        "meteor_count": result.meteor_count,
        "line_count": result.line_count,
        "lines": result.lines,
    }


# ── focus config ─────────────────────────────────────────────────


@router.get("/focus/config")
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
    target = paths().latest_image
    if not target.exists():
        raise HTTPException(404, "no current frame")
    cfg = load_focus_config()
    result = assess_focus(
        target, cfg.get("baseline_sharpness"), cfg.get("threshold_pct", 60)
    )
    return result

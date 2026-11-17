"""Notification channels and manual send. URLs stay under /api/notifications."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths
from app.notify.channels import Attachment, dispatch
from app.notify.store import delete_channel, load_channels, redacted_channels, upsert_channel

router = APIRouter()

@router.get("/channels")
async def list_channels():
    return {"channels": redacted_channels()}


@router.post("/channels")
async def create_channel(body: dict = Body(...)):
    body.setdefault("id", str(uuid.uuid4())[:8])
    upsert_channel(body)
    # Return redacted version — never echo raw credentials back.
    return {"ok": True, "channels": redacted_channels()}


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: str, body: dict = Body(...)):
    body["id"] = channel_id
    upsert_channel(body)
    return {"ok": True, "channels": redacted_channels()}


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

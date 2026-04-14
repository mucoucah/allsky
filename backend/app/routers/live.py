"""Live view: WS push + HTTP fallback."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from app.allsky.paths import paths
from app.allsky.status import latest_image_meta
from app.ws.manager import client_writer

router = APIRouter(prefix="/api/live", tags=["live"])
log = logging.getLogger(__name__)


@router.get("/latest.jpg")
async def latest_jpg():
    p = paths().latest_image
    if not p.exists():
        return JSONResponse({"error": "no image"}, status_code=404)
    return FileResponse(
        p,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/meta")
async def latest_meta():
    return latest_image_meta() or {}


@router.websocket("/ws")
async def live_ws(ws: WebSocket):
    broadcaster = ws.app.state.broadcaster
    await ws.accept()
    client = await broadcaster.register(ws)
    writer_task = asyncio.create_task(client_writer(client))
    try:
        # Keep the read side alive so we notice client disconnects.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        writer_task.cancel()
        try:
            await writer_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await broadcaster.unregister(client)

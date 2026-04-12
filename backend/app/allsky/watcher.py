"""Async watcher that fans out the latest image to WebSocket clients.

Uses watchfiles (which wraps inotify on Linux). When ${ALLSKY_TMP}/image.jpg
changes, we read the bytes once and hand them to the broadcaster — every
connected client gets the same buffer, so 1 read serves N viewers.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from watchfiles import Change, awatch

from app.config import get_settings

from .paths import paths
from .status import latest_image_meta

if TYPE_CHECKING:
    from app.ws.manager import LiveBroadcaster

log = logging.getLogger(__name__)


async def watch_latest_image(broadcaster: "LiveBroadcaster", stop: asyncio.Event) -> None:
    settings = get_settings()
    min_interval = 1.0 / max(settings.live_max_fps, 0.1)

    target = paths().latest_image
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    log.info("watcher: monitoring %s", target)
    last_emit = 0.0

    # Emit once at startup so newly-connected clients see the current frame
    # immediately, even if Allsky hasn't produced a new one yet.
    await _maybe_emit(broadcaster, target)

    try:
        async for changes in awatch(target_dir, stop_event=stop):
            now = time.monotonic()
            if now - last_emit < min_interval:
                continue
            relevant = any(
                p == str(target)
                and ctype in (Change.added, Change.modified)
                for ctype, p in changes
            )
            if not relevant:
                continue
            if await _maybe_emit(broadcaster, target):
                last_emit = now
    except asyncio.CancelledError:
        log.info("watcher: cancelled")
        raise
    except Exception:
        log.exception("watcher: unexpected error")


async def _maybe_emit(broadcaster: "LiveBroadcaster", target) -> bool:
    if not target.exists():
        return False
    try:
        data = target.read_bytes()
    except OSError as e:
        log.warning("watcher: failed to read %s: %s", target, e)
        return False
    meta = latest_image_meta() or {}
    await broadcaster.broadcast_frame(data, meta)
    return True

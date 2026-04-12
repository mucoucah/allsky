"""WebSocket fan-out for the live view.

Per-client send queues are bounded — a slow consumer doesn't back-pressure the
producer (the inotify watcher), it just drops frames for itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

QUEUE_MAX = 4  # frames; ~2 MB at typical sizes — small on purpose


@dataclass(eq=False)
class Client:
    ws: WebSocket
    queue: asyncio.Queue[tuple[str, Any]]  # ("frame", bytes) or ("meta", dict)

    def __hash__(self) -> int:
        return id(self)


class LiveBroadcaster:
    def __init__(self) -> None:
        self._clients: set[Client] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket) -> Client:
        client = Client(ws=ws, queue=asyncio.Queue(maxsize=QUEUE_MAX))
        async with self._lock:
            self._clients.add(client)
        log.info("ws: client connected (total=%d)", len(self._clients))
        return client

    async def unregister(self, client: Client) -> None:
        async with self._lock:
            self._clients.discard(client)
        log.info("ws: client disconnected (total=%d)", len(self._clients))

    async def broadcast_frame(self, data: bytes, meta: dict) -> None:
        """Push a frame + metadata to every connected client.

        Drops oldest queued frames for clients that can't keep up.
        """
        async with self._lock:
            clients = list(self._clients)
        for c in clients:
            _try_put(c.queue, ("meta", meta))
            _try_put(c.queue, ("frame", data))

    async def broadcast_event(self, kind: str, payload: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        for c in clients:
            _try_put(c.queue, (kind, payload))

    @property
    def client_count(self) -> int:
        return len(self._clients)


def _try_put(queue: asyncio.Queue, item) -> None:
    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return


async def client_writer(client: Client) -> None:
    """Drain a client's queue to its socket. Cancelled on disconnect."""
    while True:
        kind, payload = await client.queue.get()
        try:
            if kind == "frame":
                await client.ws.send_bytes(payload)
            else:
                await client.ws.send_text(json.dumps({"type": kind, "data": payload}))
        except Exception:  # noqa: BLE001 — disconnects look like all sorts of errors
            return

"""Log viewer: tail files + live WebSocket stream of service journal."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app.allsky.paths import paths

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/allsky")
async def tail_allsky(lines: int = Query(200, ge=1, le=5000)):
    """Return the last N lines of /var/log/allsky.log."""
    p = paths().allsky_log
    if not p.exists():
        return PlainTextResponse("(log file not found)", status_code=404)
    try:
        return PlainTextResponse(_tail(str(p), lines))
    except OSError as e:
        return PlainTextResponse(f"(error reading log: {e})", status_code=500)


@router.get("/webui")
async def tail_webui(lines: int = Query(100, ge=1, le=2000)):
    """Return the last N lines of the allsky-web service journal."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", "allsky-web", "--no-pager", "-n", str(lines),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        text = (stdout or b"").decode(errors="replace")
        if not text.strip():
            text = (stderr or b"").decode(errors="replace") or "(no log output)"
        return PlainTextResponse(text)
    except Exception as e:
        return PlainTextResponse(f"(error: {e})", status_code=500)


@router.websocket("/stream")
async def log_stream(ws: WebSocket):
    """Live-stream the allsky-web journal via WebSocket.

    The client connects and receives new log lines in real time.
    Uses `journalctl -f` under the hood.
    """
    await ws.accept()
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", "allsky-web", "--no-pager", "-f", "-n", "50",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=60)
            if not line:
                break
            await ws.send_text(line.decode(errors="replace").rstrip("\n"))
    except (WebSocketDisconnect, asyncio.TimeoutError, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        if proc and proc.returncode is None:
            proc.kill()
            await proc.wait()


def _tail(filepath: str, n: int) -> str:
    """Read last n lines without loading the whole file."""
    with open(filepath, "rb") as f:
        try:
            f.seek(0, os.SEEK_END)
        except OSError:
            return ""
        size = f.tell()
        if size == 0:
            return ""
        block = min(8192, size)
        data = b""
        while True:
            pos = max(0, f.tell() - block)
            f.seek(pos)
            chunk = f.read(min(block, f.tell() + block))
            data = chunk + data
            count = data.count(b"\n")
            if count >= n + 1 or pos == 0:
                break
            f.seek(pos)
            block = min(8192, pos)
            if block == 0:
                break
        lines_list = data.decode("utf-8", errors="replace").split("\n")
        return "\n".join(lines_list[-n:])

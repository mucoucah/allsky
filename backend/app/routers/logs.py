"""Log viewer: tail the allsky log file."""
from __future__ import annotations

import os

from fastapi import APIRouter, Query
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


def _tail(filepath: str, n: int) -> str:
    """Read last n lines without loading the whole file."""
    with open(filepath, "rb") as f:
        # Seek to end.
        try:
            f.seek(0, os.SEEK_END)
        except OSError:
            return ""
        size = f.tell()
        if size == 0:
            return ""
        # Read in 8KB chunks from the end.
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

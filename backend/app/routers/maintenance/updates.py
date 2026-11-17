"""Version check. URL stays /api/maintenance/check-update."""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter

from app.allsky.paths import paths

router = APIRouter()

@router.get("/check-update")
async def check_update():
    """Check GitHub for a newer Allsky version."""
    # Read installed version from version file.
    p = paths()
    installed = "unknown"
    try:
        if p.version_file.exists():
            installed = p.version_file.read_text().splitlines()[0].strip()
    except OSError:
        pass

    # Fetch latest from GitHub.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://raw.githubusercontent.com/thomasjacquin/allsky/master/version",
                follow_redirects=True,
            )
            latest = r.text.strip().splitlines()[0] if r.text else "unknown"
    except Exception as e:
        return {"installed": installed, "latest": None, "error": str(e)}

    # Also check our web UI version.
    from app import __version__ as web_version
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://raw.githubusercontent.com/mucoucah/allsky/main/backend/app/__init__.py",
                follow_redirects=True,
            )
            m = re.search(r'__version__\s*=\s*"([^"]+)"', r.text)
            web_latest = m.group(1) if m else None
    except Exception:
        web_latest = None

    return {
        "installed": installed,
        "latest": latest,
        "update_available": installed != latest and installed != "unknown",
        "web_version": web_version,
        "web_latest": web_latest,
        "web_update_available": web_latest is not None and web_version != web_latest,
    }

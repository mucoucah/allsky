"""Overlay editor endpoints. URLs stay under /api/maintenance/overlay.

The editor is not in the web menu. These routes remain for existing clients.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths
from app.allsky.settings import load_values

router = APIRouter()

@router.get("/overlay/debug")
async def overlay_debug():
    """Diagnostic info for why the overlay might not be working."""
    from app.allsky.settings import load_values
    p = paths()
    info: dict[str, Any] = {
        "allsky_home": str(p.home),
    }

    # Check overlay method setting.
    values = load_values()
    info["overlaymethod"] = values.get("overlaymethod")
    info["overlaymethod_note"] = "0=legacy, 1=module (needed for overlay editor)"

    # Check venv.
    venv = p.home / "venv"
    info["venv_exists"] = _safe_exists(venv)
    if info["venv_exists"]:
        # Check for key packages.
        pip = venv / "bin" / "pip"
        if _safe_exists(pip):
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(pip), "list", "--format=freeze",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                pkgs = {l.split("==")[0].lower(): l.split("==")[1] if "==" in l else ""
                        for l in stdout.decode(errors="replace").splitlines() if l}
                info["python_packages"] = {
                    "pillow": pkgs.get("pillow"),
                    "ephem": pkgs.get("ephem"),
                    "skyfield": pkgs.get("skyfield"),
                    "opencv-python": pkgs.get("opencv-python") or pkgs.get("opencv-python-headless"),
                    "numpy": pkgs.get("numpy"),
                }
            except Exception as e:
                info["pip_check_error"] = str(e)

    # Check overlay config.
    overlay_dir = p.config / "overlay"
    info["overlay_config_dir"] = str(overlay_dir)
    info["overlay_config_dir_exists"] = _safe_exists(overlay_dir)
    if info["overlay_config_dir_exists"]:
        try:
            info["overlay_config_files"] = [x.name for x in overlay_dir.rglob("*.json") if x.is_file()]
        except OSError:
            pass

    # Check modules dir.
    modules_dir = p.scripts / "modules"
    info["modules_dir"] = str(modules_dir)
    info["allsky_overlay_py_exists"] = _safe_exists(modules_dir / "allsky_overlay.py")
    info["flow_runner_py_exists"] = _safe_exists(p.scripts / "flow-runner.py")

    # Check recent allsky log for overlay errors.
    log_path = Path("/var/log/allsky.log")
    overlay_lines: list[str] = []
    if _safe_exists(log_path):
        try:
            with log_path.open() as f:
                lines = f.readlines()[-500:]
            overlay_lines = [l.strip() for l in lines
                             if "overlay" in l.lower() or "flow-runner" in l.lower()]
        except OSError:
            pass
    # Fallback to journalctl if no /var/log/allsky.log.
    if not overlay_lines:
        try:
            proc = await asyncio.create_subprocess_exec(
                "journalctl", "-u", "allsky", "--no-pager", "-n", "500",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            text = stdout.decode(errors="replace")
            overlay_lines = [
                l.strip() for l in text.splitlines()
                if "overlay" in l.lower() or "flow-runner" in l.lower()
                or "saveimage" in l.lower() or "loadimage" in l.lower()
                or "module" in l.lower() and ("error" in l.lower() or "fail" in l.lower() or "traceback" in l.lower())
            ]
        except Exception as e:
            info["journalctl_error"] = str(e)

    info["recent_overlay_log_lines"] = overlay_lines[-30:]

    # Check ownership/permissions of the overlay config dir (the service user
    # needs to be able to read these).
    try:
        st = overlay_dir.stat()
        info["overlay_dir_mode"] = oct(st.st_mode)
        import pwd
        try:
            info["overlay_dir_owner"] = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            info["overlay_dir_owner"] = str(st.st_uid)
    except OSError:
        pass

    # Check if allsky service is actually running.
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", "allsky.service",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        info["allsky_service_active"] = stdout.decode(errors="replace").strip()
    except Exception:
        pass

    return info


# ── Overlay configuration ───────────────────────────────────────

@router.get("/overlay/config")
async def get_overlay_config():
    """Return the current overlay configuration (module-style)."""
    config_dir = paths().config / "overlay" / "config"
    result = {
        "config_dir": str(config_dir),
        "exists": config_dir.exists() if _safe_exists(config_dir) else False,
        "fields": [],
        "configs": [],
    }
    if not _safe_exists(config_dir):
        return result

    import json as _json
    # Load fields.json (the menu of data points).
    fields_path = config_dir / "fields.json"
    if _safe_exists(fields_path):
        try:
            with fields_path.open() as f:
                result["fields"] = _json.load(f)
        except Exception as e:
            result["fields_error"] = str(e)

    # List available overlay configs (overlay-RPi.json, overlay-ZWO.json, etc.)
    try:
        for p in config_dir.iterdir():
            if p.is_file() and p.suffix == ".json" and p.name.startswith("overlay-"):
                result["configs"].append(p.name)
    except OSError:
        pass

    return result


@router.get("/overlay/layout/{name}")
async def get_overlay_layout(name: str):
    """Return the overlay layout JSON for a specific config."""
    if "/" in name or ".." in name:
        raise HTTPException(400, "invalid name")
    p = paths().config / "overlay" / "config" / name
    if not _safe_exists(p):
        raise HTTPException(404, f"not found: {p}")
    import json as _json
    try:
        with p.open() as f:
            return _json.load(f)
    except Exception as e:
        raise HTTPException(500, f"failed to read: {e}")


@router.put("/overlay/layout/{name}")
async def put_overlay_layout(name: str, body: Any = Body(...)):
    """Save an overlay layout JSON."""
    if "/" in name or ".." in name or not name.endswith(".json"):
        raise HTTPException(400, "invalid name (must be .json)")
    p = paths().config / "overlay" / "config" / name
    import json as _json
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with tmp.open("w") as f:
            _json.dump(body, f, indent=2)
        os.replace(str(tmp), str(p))
    except Exception as e:
        raise HTTPException(500, f"save failed: {e}")
    return {"ok": True}


# ── helpers ─────────────────────────────────────────────────────

def _safe_exists(p: Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False

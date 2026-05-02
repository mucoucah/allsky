"""Extended maintenance endpoints: darks, updates, uploads, generate for day.

These bridge the upstream Allsky tooling (scripts) with the web UI, exposing
features that were previously only available via command line.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from app.allsky.paths import paths
from app.allsky.settings import load_values, save_values

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


# ── Update check ────────────────────────────────────────────────

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
                "https://raw.githubusercontent.com/mucoucah/allsky/claude/rewrite-allsky-web-interface-qrpXs/backend/app/__init__.py",
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


# ── Dark frames ─────────────────────────────────────────────────

@router.get("/darks")
async def list_darks():
    """List captured dark frames."""
    darks_dir = paths().darks
    out: list[dict] = []
    try:
        if not darks_dir.exists():
            return {"darks": [], "darks_dir": str(darks_dir), "total_bytes": 0}
    except OSError:
        return {"darks": [], "darks_dir": str(darks_dir), "total_bytes": 0}

    total_bytes = 0
    try:
        for p in sorted(darks_dir.iterdir(), reverse=True):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".raw"}:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            # Try to extract temperature from filename (e.g. "20.jpg", "-5.jpg").
            temp_match = re.match(r"^(-?\d+(?:\.\d+)?)\.", p.name)
            temp = float(temp_match.group(1)) if temp_match else None
            out.append({
                "name": p.name,
                "size_bytes": st.st_size,
                "mtime": int(st.st_mtime),
                "temperature_c": temp,
            })
            total_bytes += st.st_size
    except OSError as e:
        log.warning("list_darks: %s", e)

    return {"darks": out, "darks_dir": str(darks_dir), "total_bytes": total_bytes}


@router.get("/darks/{name}")
async def get_dark(name: str):
    """Serve a dark frame file."""
    if "/" in name or ".." in name:
        raise HTTPException(400, "invalid name")
    p = paths().darks / name
    if not p.exists():
        raise HTTPException(404, "not found")
    return FileResponse(str(p))


@router.delete("/darks/{name}")
async def delete_dark(name: str):
    """Delete a dark frame file."""
    if "/" in name or ".." in name:
        raise HTTPException(400, "invalid name")
    p = paths().darks / name
    if not p.exists():
        raise HTTPException(404, "not found")
    try:
        p.unlink()
    except OSError as e:
        raise HTTPException(500, f"delete failed: {e}")
    return {"deleted": name}


@router.post("/darks/capture")
async def capture_dark():
    """Enable dark frame capture mode and restart the service."""
    values = load_values()
    values["takedarkframes"] = "true"
    values["lastchanged"] = "1"
    save_values(values)

    # Restart the camera service so it picks up dark capture mode.
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", "/usr/bin/systemctl", "restart", "allsky.service",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "message": "Dark frame capture enabled. The camera will capture darks. "
                   "Turn off 'takedarkframes' in Settings when done.",
    }


# ── Upload / Remote Website ─────────────────────────────────────

@router.post("/upload/test")
async def test_upload(body: dict = Body(...)):
    """Test upload configuration by uploading a small test file."""
    upload_type = body.get("type", "remote-web")  # local-web, remote-web, remote-server

    # Save the upload settings first.
    values = load_values()
    for k, v in body.items():
        if k == "type":
            continue
        # Prefix upload-related keys to match settings schema.
        values[k] = v
    save_values(values)

    # Create a test file.
    tmp = paths().tmp
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    test_file = tmp / "upload_test.txt"
    test_file.write_text(f"Allsky upload test\n")

    # Run testUpload.sh
    script = paths().scripts / "testUpload.sh"
    if not script.exists():
        raise HTTPException(500, f"testUpload.sh not found at {script}")

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(script), f"--{upload_type}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ALLSKY_HOME": str(paths().home)},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = (stdout + stderr).decode(errors="replace")
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": output[-4000:],  # tail in case of huge output
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Upload test timed out after 60s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Generate for past date ──────────────────────────────────────

@router.get("/generate/dates")
async def available_dates():
    """List dates with images available for regeneration."""
    images_dir = paths().images
    dates: list[str] = []
    try:
        if images_dir.exists():
            for p in sorted(images_dir.iterdir(), reverse=True):
                if p.is_dir() and re.match(r"^\d{8}$", p.name):
                    # Count images in the directory.
                    try:
                        count = sum(1 for f in p.iterdir() if f.is_file() and
                                    f.suffix.lower() in {".jpg", ".jpeg", ".png"})
                        dates.append({"date": p.name, "image_count": count})
                    except OSError:
                        pass
    except OSError:
        pass
    return {"dates": dates}


@router.post("/generate/{date}")
async def generate_for_date(date: str, body: dict = Body(...)):
    """Regenerate keogram, startrail, or timelapse for a given date (YYYYMMDD)."""
    if not re.match(r"^\d{8}$", date):
        raise HTTPException(400, "date must be YYYYMMDD")

    kinds = body.get("kinds", ["keogram", "startrails", "timelapse"])
    if isinstance(kinds, str):
        kinds = [kinds]

    script = paths().scripts / "generateForDay.sh"
    if not script.exists():
        raise HTTPException(500, "generateForDay.sh not found")

    # Build args.
    args = ["bash", str(script)]
    if "keogram" in kinds:
        args.append("--keogram")
    if "startrails" in kinds:
        args.append("--startrails")
    if "timelapse" in kinds:
        args.append("--timelapse")
    args.append(date)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ALLSKY_HOME": str(paths().home)},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1800)  # 30 min
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "kinds": kinds,
            "date": date,
            "output": (stdout + stderr).decode(errors="replace")[-4000:],
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Generation timed out after 30 minutes"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Overlay debug ───────────────────────────────────────────────

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


# ── Daily-lapse ────────────────────────────────────────────────

@router.post("/dailylapse/preview")
async def dailylapse_preview(body: dict = Body(...)):
    """Collect matching frames without generating video — for preview."""
    from app.allsky.dailylapse import collect_frames
    mode = body.get("mode", "fixed")
    clock_time = body.get("clock_time", "12:00")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    max_offset = body.get("max_offset_min", 30)
    frames = collect_frames(mode, clock_time, start_date, end_date, max_offset)
    return {
        "frame_count": len(frames),
        "frames": [
            {
                "date": f.date_dir,
                "target_time": f.target_time.isoformat(),
                "actual_time": f.actual_time.isoformat(),
                "offset_sec": f.offset_sec,
                "filename": f.path.name,
            }
            for f in frames
        ],
    }


_dailylapse_lock = asyncio.Lock()
_dailylapse_progress: dict = {"status": "idle"}


@router.post("/dailylapse/generate")
async def dailylapse_generate(body: dict = Body(...)):
    """Generate a daily-lapse video."""
    from app.allsky.dailylapse import collect_frames, generate_dailylapse

    if _dailylapse_lock.locked():
        raise HTTPException(409, "Daily-lapse generation already in progress")

    mode = body.get("mode", "fixed")
    clock_time = body.get("clock_time", "12:00")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    max_offset = body.get("max_offset_min", 30)
    fps = body.get("fps", 10)
    label = body.get("label", mode)

    frames = collect_frames(mode, clock_time, start_date, end_date, max_offset)
    if len(frames) < 2:
        raise HTTPException(400, f"Need at least 2 frames, found {len(frames)}")

    out_dir = paths().allsky_home / "images" / "dailylapse"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^a-zA-Z0-9_-]", "", label)[:30] or "daily"
    out_file = out_dir / f"dailylapse-{safe_label}.mp4"

    async with _dailylapse_lock:
        _dailylapse_progress.update(status="generating", frames=len(frames), label=label)
        try:
            ok = await generate_dailylapse(frames, out_file, fps=fps)
        finally:
            _dailylapse_progress.update(status="idle")

    if not ok:
        raise HTTPException(500, "ffmpeg failed — check logs")

    return {
        "ok": True,
        "frames_used": len(frames),
        "date_range": f"{frames[0].date_dir} – {frames[-1].date_dir}",
        "video_url": f"/api/maintenance/dailylapse/video/{safe_label}",
    }


@router.get("/dailylapse/status")
async def dailylapse_status():
    return dict(_dailylapse_progress)


@router.get("/dailylapse/list")
async def dailylapse_list():
    """List previously generated daily-lapse videos."""
    out_dir = paths().allsky_home / "images" / "dailylapse"
    if not out_dir.exists():
        return {"videos": []}
    videos = []
    for f in sorted(out_dir.iterdir()):
        if f.suffix == ".mp4":
            stat = f.stat()
            videos.append({
                "name": f.stem,
                "size_mb": round(stat.st_size / 1_048_576, 1),
                "created": stat.st_mtime,
                "url": f"/api/maintenance/dailylapse/video/{f.stem.replace('dailylapse-', '')}",
            })
    return {"videos": videos}


@router.get("/dailylapse/video/{label}")
async def dailylapse_video(label: str):
    safe_label = re.sub(r"[^a-zA-Z0-9_-]", "", label)[:30]
    out_dir = paths().allsky_home / "images" / "dailylapse"
    video = out_dir / f"dailylapse-{safe_label}.mp4"
    if not video.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(video, media_type="video/mp4", filename=video.name)


@router.delete("/dailylapse/video/{label}")
async def dailylapse_delete(label: str):
    safe_label = re.sub(r"[^a-zA-Z0-9_-]", "", label)[:30]
    out_dir = paths().allsky_home / "images" / "dailylapse"
    video = out_dir / f"dailylapse-{safe_label}.mp4"
    if video.exists():
        video.unlink()
    return {"ok": True}

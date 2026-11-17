"""Daily-lapse preview, generate, and playback. URLs stay under /api/maintenance."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from app.allsky.paths import paths

router = APIRouter()

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

"""Daily-lapse: timelapse from one image per day at the same time.

Picks the frame closest to a target moment each day (fixed clock time,
sunrise, sunset, or solar noon) and stitches them into a video with ffmpeg.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import ephem

from .images import DATE_DIR_RE, IMAGE_EXTS, list_date_dirs
from .paths import paths
from .settings import load_settings

log = logging.getLogger(__name__)


@dataclass
class DailyFrame:
    date_dir: str
    path: Path
    target_time: datetime
    actual_time: datetime
    offset_sec: int


def _get_observer() -> ephem.Observer | None:
    settings = load_settings()
    lat_str = settings.get("latitude", "")
    lon_str = settings.get("longitude", "")

    def parse(s: str, neg: str) -> float | None:
        s = str(s).strip()
        if not s:
            return None
        sign = -1 if s.upper().endswith(neg) else 1
        s = s.rstrip("NSEWnsew").strip()
        try:
            return float(s) * sign
        except ValueError:
            return None

    lat = parse(lat_str, "S")
    lon = parse(lon_str, "W")
    if lat is None or lon is None:
        return None
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.pressure = 0
    return obs


def _sun_event_utc(obs: ephem.Observer, d: date, event: str) -> datetime | None:
    """Compute sunrise, sunset, or solar noon for a given date."""
    obs = obs.copy()
    obs.date = ephem.Date(datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc))
    obs.horizon = "0"
    sun = ephem.Sun()
    try:
        if event == "sunrise":
            result = obs.previous_rising(sun)
        elif event == "sunset":
            result = obs.next_setting(sun)
        elif event == "solar_noon":
            result = obs.next_transit(sun)
        else:
            return None
        return ephem.Date(result).datetime().replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _target_for_day(d: date, mode: str, clock_time: str, obs: ephem.Observer | None) -> datetime | None:
    """Return the target UTC datetime for a given day and mode."""
    if mode == "fixed":
        try:
            parts = clock_time.split(":")
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            h, m = 12, 0
        return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
    if obs is None:
        return None
    return _sun_event_utc(obs, d, mode)


def _find_closest_image(day_dir: Path, target_utc: datetime, max_offset_min: int = 30) -> tuple[Path, datetime, int] | None:
    """Find the image file closest in time to target_utc within a day directory."""
    if not day_dir.exists():
        return None
    candidates: list[tuple[Path, float]] = []
    for p in day_dir.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("."):
            candidates.append((p, p.stat().st_mtime))
    if not candidates:
        return None

    target_ts = target_utc.timestamp()
    best_path, best_mtime = min(candidates, key=lambda x: abs(x[1] - target_ts))
    offset = int(abs(best_mtime - target_ts))
    if max_offset_min > 0 and offset > max_offset_min * 60:
        return None
    actual = datetime.fromtimestamp(best_mtime, tz=timezone.utc)
    return best_path, actual, offset


def collect_frames(
    mode: str = "fixed",
    clock_time: str = "12:00",
    start_date: str | None = None,
    end_date: str | None = None,
    max_offset_min: int = 30,
) -> list[DailyFrame]:
    """Collect one frame per day matching the target time."""
    obs = _get_observer()
    if mode != "fixed" and obs is None:
        log.warning("No lat/lon configured — cannot compute %s", mode)
        return []

    all_dirs = list_date_dirs()
    images_base = paths().images

    frames: list[DailyFrame] = []
    for dd in sorted(all_dirs):
        if start_date and dd < start_date:
            continue
        if end_date and dd > end_date:
            continue
        try:
            d = date(int(dd[:4]), int(dd[4:6]), int(dd[6:8]))
        except ValueError:
            continue

        target = _target_for_day(d, mode, clock_time, obs)
        if target is None:
            continue

        result = _find_closest_image(images_base / dd, target, max_offset_min)
        if result is None:
            continue

        img_path, actual, offset = result
        frames.append(DailyFrame(
            date_dir=dd,
            path=img_path,
            target_time=target,
            actual_time=actual,
            offset_sec=offset,
        ))

    return frames


async def generate_dailylapse(
    frames: list[DailyFrame],
    output_path: Path,
    fps: int = 10,
    width: int = 0,
    height: int = 0,
) -> bool:
    """Generate a video from daily frames using ffmpeg."""
    if len(frames) < 2:
        log.warning("Need at least 2 frames, got %d", len(frames))
        return False

    tmpdir = tempfile.mkdtemp(prefix="dailylapse-")
    try:
        for i, frame in enumerate(frames):
            ext = frame.path.suffix
            link = Path(tmpdir) / f"{i:05d}{ext}"
            os.symlink(frame.path, link)

        ext = frames[0].path.suffix
        scale = ""
        if width > 0 and height > 0:
            scale = f"-filter:v scale={width}:{height}"
        elif width > 0:
            scale = f"-filter:v scale={width}:-2"

        cmd = (
            f"ffmpeg -y -f image2 -r {fps} "
            f"-i '{tmpdir}/%05d{ext}' "
            f"-vcodec libx264 -pix_fmt yuv420p -movflags +faststart "
            f"{scale} '{output_path}'"
        )
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            log.error("ffmpeg failed: %s", stderr.decode()[-500:])
            return False
        return output_path.exists()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

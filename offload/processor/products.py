"""Keogram, startrails, and timelapse for one night.

Keogram is the center column of each night frame. Startrails is a lighten
blend (per-pixel maximum). Timelapse is ffmpeg, preferring h264_nvenc.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from offload.processor.encode import encoder_args, parse_encoders, timelapse_command

log = logging.getLogger("allsky-processor")


def product_paths(data_dir: Path, date: str) -> dict[str, Path]:
    day = data_dir / "images" / date
    return {
        "frames": day,
        "keogram": day / "keogram" / f"keogram-{date}.jpg",
        "startrails": day / "startrails" / f"startrails-{date}.jpg",
        "timelapse": day / f"allsky-{date}.mp4",
        "meteors": data_dir / "html" / "allsky" / "meteors" / date,
        "latest": data_dir / "tmp" / "image.jpg",
    }


def night_frames(day_dir: Path) -> list[Path]:
    frames = sorted(day_dir.glob("N_*.jpg"))
    if frames:
        return frames
    return sorted(path for path in day_dir.glob("*.jpg") if path.is_file())


def _write_jpeg(path: Path, image) -> bool:
    import cv2
    path.parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90]))


def build_keogram(frames: list[Path], dest: Path) -> bool:
    import cv2
    import numpy as np

    columns = []
    height = None
    for path in frames:
        image = cv2.imread(str(path))
        if image is None:
            continue
        if height is None:
            height = image.shape[0]
        elif image.shape[0] != height:
            image = cv2.resize(image, (image.shape[1], height))
        x = image.shape[1] // 2
        columns.append(image[:, x:x + 1])
    if not columns:
        return False
    stacked = np.hstack(columns)
    return _write_jpeg(dest, stacked)


def build_startrails(frames: list[Path], dest: Path) -> bool:
    import cv2
    import numpy as np

    accumulator = None
    for path in frames:
        image = cv2.imread(str(path))
        if image is None:
            continue
        if accumulator is None:
            accumulator = image.astype(np.uint16)
            continue
        if image.shape != accumulator.shape:
            image = cv2.resize(image, (accumulator.shape[1], accumulator.shape[0]))
        accumulator = np.maximum(accumulator, image.astype(np.uint16))
    if accumulator is None:
        return False
    return _write_jpeg(dest, accumulator.astype(np.uint8))


def probe_encoders() -> set[str]:
    try:
        completed = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"libx264"}
    return parse_encoders(completed.stdout + completed.stderr) or {"libx264"}


def build_timelapse(frames: list[Path], dest: Path, preference: str) -> bool:
    if not frames or shutil.which("ffmpeg") is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_file = dest.with_suffix(".txt")
    lines = []
    for path in frames:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n")
    args = encoder_args(preference, probe_encoders())
    cmd = timelapse_command(str(list_file), str(dest), args)
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("ffmpeg failed to run: %s", exc)
        return False
    if completed.returncode != 0:
        log.warning("ffmpeg exit %s: %s", completed.returncode, (completed.stderr or "")[-400:])
        if args[1] != "libx264":
            cmd = timelapse_command(str(list_file), str(dest), encoder_args("libx264", {"libx264"}))
            try:
                completed = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600, check=False)
            except (OSError, subprocess.TimeoutExpired):
                return False
            return completed.returncode == 0 and dest.is_file()
        return False
    return dest.is_file()


def build_night_products(data_dir: Path, date: str, encoder: str) -> dict[str, bool]:
    paths = product_paths(data_dir, date)
    frames = night_frames(paths["frames"])
    results = {
        "keogram": False,
        "startrails": False,
        "timelapse": False,
    }
    if not frames:
        log.info("no frames for %s", date)
        return results
    try:
        results["keogram"] = build_keogram(frames, paths["keogram"])
        results["startrails"] = build_startrails(frames, paths["startrails"])
    except Exception:
        log.exception("still products failed for %s", date)
    results["timelapse"] = build_timelapse(frames, paths["timelapse"], encoder)
    log.info("night %s products %s (%d frames)", date, results, len(frames))
    return results

"""Background watcher loops that fire alerts through the notification infra.

Two watchers run as asyncio tasks during the FastAPI lifespan:
  1. Meteor watcher — runs detection on tmp/image.jpg after every new frame,
     fires an alert (with optional annotated snapshot + timelapse) when streaks
     are found.
  2. Focus watcher — periodically computes a sharpness score and alerts if
     it stays below the calibrated baseline for N consecutive checks.

Both watchers are gated by their respective config enable flags.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from pathlib import Path

from app.allsky.paths import paths
from app.db import connect, insert_alert

from .channels import Attachment, dispatch
from .focus import assess_focus
from .meteor import detect as detect_meteor
from .store import load_channels, load_comet_config, load_focus_config

log = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────

def _read_file(path: Path, max_mb: float = 10.0) -> bytes | None:
    if not path.exists():
        return None
    try:
        if path.stat().st_size > max_mb * 1024 * 1024:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _build_attachments(
    include_snapshot: bool, include_timelapse: bool,
) -> list[Attachment]:
    atts: list[Attachment] = []
    if include_snapshot:
        data = _read_file(paths().latest_image)
        if data:
            atts.append(Attachment("latest.jpg", data, "image/jpeg"))
    if include_timelapse:
        tl = paths().tmp / "mini-timelapse.mp4"
        data = _read_file(tl)
        if data:
            atts.append(Attachment("timelapse.mp4", data, "video/mp4"))
    return atts


# ── meteor watcher ───────────────────────────────────────────────

async def meteor_watcher(stop: asyncio.Event) -> None:
    """Watch for new frames and run meteor detection on each one."""
    log.info("meteor_watcher: starting")
    last_mtime: float = 0.0

    while not stop.is_set():
        try:
            cfg = load_comet_config()  # reloaded each iteration for live changes
            if not cfg.get("enabled"):
                await _sleep(stop, 30)
                continue

            target = paths().latest_image
            if not target.exists():
                await _sleep(stop, 10)
                continue

            mtime = target.stat().st_mtime
            if mtime <= last_mtime:
                await _sleep(stop, 5)
                continue
            last_mtime = mtime

            min_length = cfg.get("min_streak_length", 100)
            # Find the mask file if it exists.
            mask_path = paths().masks_dir / "mask.png"
            result = detect_meteor(
                target, min_length=min_length, annotate=True,
                mask_path=mask_path if mask_path.exists() else None,
            )
            if result.meteor_count > 0:
                # Dedup: one alert per day.
                today = date.today().isoformat()
                if await _already_alerted("meteor", today):
                    await _sleep(stop, cfg.get("poll_interval_minutes", 15) * 60)
                    continue

                await _record_alert("meteor", today)
                await insert_alert("info", "meteor", f"{result.meteor_count} meteor(s) detected")

                channels = load_channels()
                atts: list[Attachment] = []
                if result.annotated_jpeg:
                    atts.append(Attachment("meteor_detected.jpg", result.annotated_jpeg, "image/jpeg"))
                if cfg.get("include_timelapse"):
                    tl = _read_file(paths().tmp / "mini-timelapse.mp4")
                    if tl:
                        atts.append(Attachment("timelapse.mp4", tl, "video/mp4"))

                subject = f"Meteor detected ({result.meteor_count})"
                body = (
                    f"{result.meteor_count} meteor streak(s) found in the latest allsky frame.\n"
                    f"Lines detected: {result.line_count}."
                )
                await dispatch(channels, subject, body, atts)
                log.info("meteor_watcher: alerted %d meteor(s)", result.meteor_count)

            poll = cfg.get("poll_interval_minutes", 15)
            await _sleep(stop, poll * 60)

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("meteor_watcher: error")
            await _sleep(stop, 60)

    log.info("meteor_watcher: stopped")


# ── focus watcher ────────────────────────────────────────────────

async def focus_watcher(stop: asyncio.Event) -> None:
    log.info("focus_watcher: starting")
    consecutive_soft = 0

    while not stop.is_set():
        try:
            cfg = load_focus_config()
            if not cfg.get("enabled"):
                consecutive_soft = 0
                await _sleep(stop, 30)
                continue

            target = paths().latest_image
            if not target.exists():
                await _sleep(stop, 10)
                continue

            baseline = cfg.get("baseline_sharpness")
            threshold_pct = cfg.get("threshold_pct", 60)
            needed = cfg.get("consecutive_failures_to_alert", 5)

            mask_path = paths().masks_dir / "mask.png"
            result = assess_focus(
                target, baseline, threshold_pct,
                mask_path=mask_path if mask_path.exists() else None,
            )
            if result["status"] == "soft":
                consecutive_soft += 1
                log.debug("focus_watcher: soft (%d/%d)", consecutive_soft, needed)
                if consecutive_soft >= needed:
                    today = date.today().isoformat()
                    if not await _already_alerted("focus", today):
                        await _record_alert("focus", today)
                        await insert_alert(
                            "warning", "focus",
                            f"Camera may be out of focus (score {result['score']}, "
                            f"baseline {result['baseline']}, threshold {result['threshold']})"
                        )
                        channels = load_channels()
                        atts = _build_attachments(cfg.get("include_snapshot", True), False)
                        subject = "Allsky: camera may be out of focus"
                        body = (
                            f"Sharpness score {result['score']} is below the threshold "
                            f"{result['threshold']} (baseline {result['baseline']}) for "
                            f"{consecutive_soft} consecutive checks."
                        )
                        await dispatch(channels, subject, body, atts)
                        log.info("focus_watcher: alerted (score=%s)", result["score"])
            else:
                if consecutive_soft > 0:
                    log.debug("focus_watcher: back to normal")
                consecutive_soft = 0

            poll = cfg.get("poll_interval_minutes", 5)
            await _sleep(stop, poll * 60)

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("focus_watcher: error")
            await _sleep(stop, 60)

    log.info("focus_watcher: stopped")


# ── dedup helpers ────────────────────────────────────────────────

async def _already_alerted(kind: str, day: str) -> bool:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM alert_dedup WHERE kind=? AND day=?", (kind, day)
        )
        return (await cur.fetchone()) is not None


async def _record_alert(kind: str, day: str) -> None:
    async with connect() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO alert_dedup(kind, day) VALUES(?, ?)", (kind, day)
        )
        await conn.commit()


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    """Sleep that wakes early if stop is set."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass

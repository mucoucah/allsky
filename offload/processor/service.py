"""Processor loop: stable incoming files, meteors, end-of-night products, retention."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from offload.config import OffloadConfig, load_config
from offload.frames import FrameRef
from offload.processor.detect import NightDetector
from offload.processor.disk_guard import (
    HYSTERESIS_GB,
    disk_free_gb,
    guard_is_active,
    guard_timestamp,
)
from offload.processor.products import build_night_products, product_paths
from offload.processor.retention import dates_over_budget, directory_size, prune_raw_frames
from offload.processor.watch import (
    BookState,
    dispatch_order,
    due_nights,
    load_ready,
    ready_names,
    snapshot_sizes,
)

log = logging.getLogger("allsky-processor")

RETENTION_INTERVAL_SECONDS = 3600.0


def _state_path(cfg: OffloadConfig) -> Path:
    return Path(cfg.processor.data_dir) / "config" / "processor_state.json"


def load_state(cfg: OffloadConfig) -> dict:
    path = _state_path(cfg)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(cfg: OffloadConfig, data: dict) -> None:
    path = _state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def load_books(cfg: OffloadConfig) -> BookState:
    data = load_state(cfg)
    state = BookState()
    state.finalized = set(data.get("finalized") or [])
    return state


def save_books(cfg: OffloadConfig, state: BookState) -> None:
    data = load_state(cfg)
    data["finalized"] = sorted(state.finalized)
    save_state(cfg, data)


def _mask_path(cfg: OffloadConfig, incoming: Path) -> Path | None:
    candidates = [
        incoming / "mask.png",
        Path(cfg.processor.data_dir) / "config" / "overlay" / "images" / "mask.png",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _use_cuda(setting: str) -> bool:
    return setting != "off"


def publish_latest(source: Path, data_dir: Path) -> Path:
    """Copy a frame to the live-view image. The source file is left in place."""
    latest = data_dir / "tmp" / "image.jpg"
    latest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, latest, follow_symlinks=True)
    return latest


def discard_incoming(frame: FrameRef) -> None:
    """Remove a finished incoming file so the Pi outbox can delete its copy."""
    path = frame.path
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
    except OSError:
        log.warning("could not remove incoming frame %s", path)


def archive_frame(frame: FrameRef, data_dir: Path) -> Path:
    dest_dir = data_dir / "images" / frame.bucket
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / frame.name
    if dest.exists() and frame.path.resolve() != dest.resolve():
        dest.unlink()
    if frame.path.resolve() != dest.resolve():
        shutil.move(str(frame.path), str(dest))
    publish_latest(dest, data_dir)
    return dest


def apply_retention(cfg: OffloadConfig, now: datetime | None = None) -> list[str]:
    """Delete expired raw frames. Kept products and meteor hits stay on disk.

    The age window is processor.raw_retention_days. The disk budget still
    selects the oldest day directories, but only their raw frames are removed.
    """
    data = Path(cfg.processor.data_dir)
    images = data / "images"
    moment = now or datetime.now()
    extra: list[str] = []
    if images.is_dir() and cfg.processor.max_disk_bytes > 0:
        dates = sorted(
            path.name for path in images.iterdir()
            if path.is_dir() and not path.is_symlink() and len(path.name) == 8 and path.name.isdigit()
        )
        sizes = {date: directory_size(images / date) for date in dates}
        extra = dates_over_budget(dates, sizes, cfg.processor.max_disk_bytes)
    result = prune_raw_frames(
        data,
        today=moment,
        keep_days=int(cfg.processor.raw_retention_days),
        extra_dates=extra,
    )
    return result.removed


def process_batch(
    frames: list[FrameRef],
    state: BookState,
    *,
    now_epoch: float,
    quiet_with_day_seconds: int,
    quiet_alone_seconds: int,
    night_priority: bool,
    on_night,
    on_archive,
    on_finalize,
) -> list[str]:
    """Dispatch ready frames. Callbacks keep the unit test off OpenCV and ffmpeg."""
    finalized: list[str] = []
    for frame in dispatch_order(frames, night_priority=night_priority):
        if frame.night:
            on_night(frame)
        on_archive(frame)
        state.note(frame, now_epoch)
    for date in due_nights(
        state,
        now_epoch,
        quiet_with_day_seconds=quiet_with_day_seconds,
        quiet_alone_seconds=quiet_alone_seconds,
    ):
        on_finalize(date)
        state.finalized.add(date)
        state.open_nights.pop(date, None)
        finalized.append(date)
    return finalized


class Processor:
    def __init__(self, cfg: OffloadConfig):
        self.cfg = cfg
        self.previous_sizes: dict[str, int] = {}
        self.state = load_books(cfg)
        self.retention_interval = RETENTION_INTERVAL_SECONDS
        self._last_retention = 0.0
        self._disk_stat_warned = False
        guard = load_state(cfg).get("disk_guard")
        if isinstance(guard, dict) and guard.get("active"):
            self.guard_active = True
            self.guard_since = guard.get("since")
        else:
            self.guard_active = False
            self.guard_since = guard.get("since") if isinstance(guard, dict) else None
        proc = cfg.processor
        self.detector = NightDetector(
            scale=proc.meteor_scale,
            min_length=proc.min_streak_length,
            use_cuda=_use_cuda(proc.use_cuda),
        )

    def run_retention(self, now: datetime | None = None) -> list[str]:
        removed = apply_retention(self.cfg, now)
        self._last_retention = time.monotonic()
        return removed

    def _retention_if_due(self, *, force: bool = False) -> list[str]:
        elapsed = time.monotonic() - self._last_retention
        if not force and self._last_retention > 0 and elapsed < self.retention_interval:
            return []
        return self.run_retention()

    def _write_guard(self, active: bool, free_gb: float | None, since: str | None) -> None:
        data = load_state(self.cfg)
        payload = {
            "active": active,
            "free_gb": None if free_gb is None else round(free_gb, 2),
            "since": since,
        }
        data["disk_guard"] = payload
        save_state(self.cfg, data)

    def _poll_disk_guard(self) -> list[str]:
        """Update the guard before ingest. Retention runs immediately when it trips."""
        data = Path(self.cfg.processor.data_dir)
        free = disk_free_gb(data)
        if free is None and not self._disk_stat_warned:
            log.warning("disk guard: could not read free space on %s", data)
            self._disk_stat_warned = True
        if free is not None:
            self._disk_stat_warned = False
        minimum = float(self.cfg.processor.min_free_gb)
        active = guard_is_active(self.guard_active, free, minimum)
        removed: list[str] = []
        if active and not self.guard_active:
            since = guard_timestamp()
            self.guard_active = True
            self.guard_since = since
            self._write_guard(True, free, since)
            shown = free if free is not None else float("nan")
            log.warning(
                "disk guard active: %.2f GB free on %s, below %.2f GB; "
                "raw frames will not be stored; meteor hits and the live image still update",
                shown,
                data,
                minimum,
            )
            removed = self.run_retention()
        elif self.guard_active and not active:
            self.guard_active = False
            self._write_guard(False, free, self.guard_since)
            shown = free if free is not None else float("nan")
            log.info(
                "disk guard cleared: %.2f GB free on %s (resume at %.2f GB); "
                "raw frames will be stored again",
                shown,
                data,
                minimum + HYSTERESIS_GB,
            )
        return removed

    def step(self, now_epoch: float | None = None) -> dict:
        removed = self._poll_disk_guard()
        removed.extend(self._retention_if_due())
        incoming = Path(self.cfg.processor.incoming_dir)
        incoming.mkdir(parents=True, exist_ok=True)
        current = snapshot_sizes(incoming)
        names = ready_names(self.previous_sizes, current)
        self.previous_sizes = current
        frames = load_ready(incoming, names)
        moment = now_epoch if now_epoch is not None else time.time()
        data = Path(self.cfg.processor.data_dir)
        mask = _mask_path(self.cfg, incoming)

        def detect(frame: FrameRef) -> None:
            when = datetime.strptime(frame.stamp, "%Y%m%d%H%M%S")
            dest = product_paths(data, frame.bucket)["meteors"]
            try:
                self.detector.feed(frame.path, when, dest, mask)
            except Exception:
                log.exception("meteor detect failed for %s", frame.name)

        def on_night(frame: FrameRef) -> None:
            if not self.guard_active:
                detect(frame)

        def on_archive(frame: FrameRef) -> None:
            if self.guard_active:
                detect(frame)
                try:
                    publish_latest(frame.path, data)
                except OSError:
                    log.warning("disk guard: live image not updated from %s", frame.name)
                discard_incoming(frame)
                return
            archive_frame(frame, data)

        def on_finalize(date: str) -> None:
            build_night_products(data, date, self.cfg.processor.encoder)

        finalized = process_batch(
            frames,
            self.state,
            now_epoch=moment,
            quiet_with_day_seconds=self.cfg.processor.quiet_with_day_seconds,
            quiet_alone_seconds=self.cfg.processor.quiet_alone_seconds,
            night_priority=self.cfg.night_priority,
            on_night=on_night,
            on_archive=on_archive,
            on_finalize=on_finalize,
        )
        if frames or finalized:
            save_books(self.cfg, self.state)
        return {
            "ready": [frame.name for frame in frames],
            "finalized": finalized,
            "removed": removed,
            "disk_guard": self.guard_active,
        }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    processor = Processor(cfg)
    log.info(
        "processor watching %s scale=%s cuda=%s raw_retention_days=%s min_free_gb=%s",
        cfg.processor.incoming_dir,
        cfg.processor.meteor_scale,
        cfg.processor.use_cuda,
        cfg.processor.raw_retention_days,
        cfg.processor.min_free_gb,
    )
    try:
        processor.run_retention()
    except Exception:
        log.exception("startup retention failed")
    while True:
        try:
            cfg = load_config()
            processor.cfg = cfg
            report = processor.step()
            if report["ready"] or report["finalized"]:
                log.info("step %s", report)
        except Exception:
            log.exception("processor step failed")
        time.sleep(max(0.5, float(load_config().processor.poll_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())

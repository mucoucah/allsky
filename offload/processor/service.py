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
from offload.processor.products import build_night_products, product_paths
from offload.processor.retention import dates_over_budget, directory_size, expired_dates
from offload.processor.watch import (
    BookState,
    dispatch_order,
    due_nights,
    load_ready,
    ready_names,
    snapshot_sizes,
)

log = logging.getLogger("allsky-processor")


def _state_path(cfg: OffloadConfig) -> Path:
    return Path(cfg.processor.data_dir) / "config" / "processor_state.json"


def load_books(cfg: OffloadConfig) -> BookState:
    path = _state_path(cfg)
    state = BookState()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    if isinstance(data, dict):
        state.finalized = set(data.get("finalized") or [])
    return state


def save_books(cfg: OffloadConfig, state: BookState) -> None:
    path = _state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"finalized": sorted(state.finalized)}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)


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


def archive_frame(frame: FrameRef, data_dir: Path) -> Path:
    dest_dir = data_dir / "images" / frame.bucket
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / frame.name
    if dest.exists() and frame.path.resolve() != dest.resolve():
        dest.unlink()
    if frame.path.resolve() != dest.resolve():
        shutil.move(str(frame.path), str(dest))
    latest = data_dir / "tmp" / "image.jpg"
    latest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dest, latest)
    return dest


def apply_retention(cfg: OffloadConfig, now: datetime | None = None) -> list[str]:
    data = Path(cfg.processor.data_dir)
    images = data / "images"
    if not images.is_dir():
        return []
    dates = sorted(
        path.name for path in images.iterdir()
        if path.is_dir() and len(path.name) == 8 and path.name.isdigit()
    )
    moment = now or datetime.now()
    remove = set(expired_dates(dates, moment, cfg.processor.retention_days))
    sizes = {date: directory_size(images / date) for date in dates}
    remove.update(dates_over_budget(dates, sizes, cfg.processor.max_disk_bytes))
    removed: list[str] = []
    for date in sorted(remove):
        for folder in (
            images / date,
            data / "html" / "allsky" / "meteors" / date,
        ):
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)
        removed.append(date)
        log.info("retention removed %s", date)
    return removed


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
        proc = cfg.processor
        self.detector = NightDetector(
            scale=proc.meteor_scale,
            min_length=proc.min_streak_length,
            use_cuda=_use_cuda(proc.use_cuda),
        )

    def step(self, now_epoch: float | None = None) -> dict:
        incoming = Path(self.cfg.processor.incoming_dir)
        incoming.mkdir(parents=True, exist_ok=True)
        current = snapshot_sizes(incoming)
        names = ready_names(self.previous_sizes, current)
        self.previous_sizes = current
        frames = load_ready(incoming, names)
        moment = now_epoch if now_epoch is not None else time.time()
        data = Path(self.cfg.processor.data_dir)
        mask = _mask_path(self.cfg, incoming)

        def on_night(frame: FrameRef) -> None:
            when = datetime.strptime(frame.stamp, "%Y%m%d%H%M%S")
            dest = product_paths(data, frame.bucket)["meteors"]
            try:
                self.detector.feed(frame.path, when, dest, mask)
            except Exception:
                log.exception("meteor detect failed for %s", frame.name)

        def on_archive(frame: FrameRef) -> None:
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
        removed = apply_retention(self.cfg)
        return {
            "ready": [frame.name for frame in frames],
            "finalized": finalized,
            "removed": removed,
        }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    processor = Processor(cfg)
    log.info(
        "processor watching %s scale=%s cuda=%s",
        cfg.processor.incoming_dir,
        cfg.processor.meteor_scale,
        cfg.processor.use_cuda,
    )
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

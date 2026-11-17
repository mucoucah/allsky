"""Move one capture file into the outbox when mode is capture-only.

Exit 0 when this script handled the frame.
Exit 2 when mode is normal so saveImage.sh continues with the usual pipeline.
Exit 1 on a real failure (the source file is left in place).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from offload.config import load_config
from offload.frames import frame_name, when_from_capture_name
from offload.sync import enforce_cap


def _period(day_or_night: str) -> str:
    return "N" if day_or_night.upper().startswith("N") else "D"


def _unique_dest(outbox: Path, when: datetime, period: str) -> Path:
    name = frame_name(when, period)
    dest = outbox / name
    if not dest.exists():
        return dest
    seq = 1
    while True:
        dest = outbox / frame_name(when, period, seq)
        if not dest.exists():
            return dest
        seq += 1


def _write_last_frame(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)


def enqueue(image: Path, day_or_night: str, tmp_dir: Path) -> int:
    cfg = load_config()
    if not cfg.capture_only:
        return 2
    if not image.is_file() or image.stat().st_size <= 0:
        print(f"enqueue: missing image {image}", file=sys.stderr)
        return 1

    period = _period(day_or_night)
    when = when_from_capture_name(image.name, datetime.fromtimestamp(image.stat().st_mtime))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    preview = tmp_dir / "image.jpg"
    try:
        shutil.copy2(image, preview)
    except OSError as exc:
        print(f"enqueue: preview copy failed: {exc}", file=sys.stderr)
        return 1

    state_path = Path(cfg.outbox_dir).parent / "last_frame.json"
    if period == "D" and cfg.drop_day_frames:
        _write_last_frame(state_path, {
            "time": when.isoformat(timespec="seconds"),
            "name": None,
            "period": period,
            "dropped": True,
        })
        if image.resolve() != preview.resolve():
            image.unlink(missing_ok=True)
        return 0

    outbox = Path(cfg.outbox_dir)
    outbox.mkdir(parents=True, exist_ok=True)
    dest = _unique_dest(outbox, when, period)
    try:
        shutil.copy2(image, dest)
    except OSError as exc:
        print(f"enqueue: outbox copy failed: {exc}", file=sys.stderr)
        return 1
    if image.resolve() != preview.resolve() and image.resolve() != dest.resolve():
        image.unlink(missing_ok=True)

    _write_last_frame(state_path, {
        "time": when.isoformat(timespec="seconds"),
        "name": dest.name,
        "period": period,
        "dropped": False,
        "bytes": dest.stat().st_size,
    })
    removed, warning = enforce_cap(outbox, cfg)
    if warning:
        print(f"enqueue: {warning}: {', '.join(removed)}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enqueue one frame for offload")
    parser.add_argument("--day-or-night", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--tmp", default="")
    args = parser.parse_args(argv)
    if args.tmp:
        tmp = Path(args.tmp)
    elif os.environ.get("ALLSKY_TMP"):
        tmp = Path(os.environ["ALLSKY_TMP"])
    elif os.environ.get("ALLSKY_HOME"):
        tmp = Path(os.environ["ALLSKY_HOME"]) / "tmp"
    else:
        tmp = Path("tmp")
    return enqueue(Path(args.image), args.day_or_night, tmp)


if __name__ == "__main__":
    sys.exit(main())

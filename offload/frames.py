"""Outbox file names, night-first ordering, and the size cap.

Night frames use Allsky's date: the calendar date 12 hours before the exposure,
so a frame taken after midnight stays with that night.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

FRAME_RE = re.compile(
    r"^(?P<period>[ND])_(?P<bucket>\d{8})_(?P<day>\d{8})_(?P<hms>\d{6})(?:_(?P<seq>\d+))?\.jpe?g$",
    re.IGNORECASE,
)
CAPTURE_RE = re.compile(r"(\d{14})")


@dataclass(frozen=True)
class FrameRef:
    path: Path
    period: str
    bucket: str
    stamp: str
    size: int

    @property
    def night(self) -> bool:
        return self.period.upper() == "N"

    @property
    def name(self) -> str:
        return self.path.name


def bucket_for(when: datetime, period: str) -> str:
    moment = when
    if period.upper() == "N":
        moment = when - timedelta(hours=12)
    return moment.strftime("%Y%m%d")


def frame_name(when: datetime, period: str, seq: int = 0) -> str:
    period = "N" if period.upper().startswith("N") else "D"
    bucket = bucket_for(when, period)
    stamp_day = when.strftime("%Y%m%d")
    hms = when.strftime("%H%M%S")
    suffix = f"_{seq}" if seq else ""
    return f"{period}_{bucket}_{stamp_day}_{hms}{suffix}.jpg"


def parse_frame_name(name: str) -> tuple[str, str, str] | None:
    match = FRAME_RE.match(name)
    if not match:
        return None
    period = match.group("period").upper()
    bucket = match.group("bucket")
    stamp = match.group("day") + match.group("hms")
    return period, bucket, stamp


def when_from_capture_name(name: str, fallback: datetime) -> datetime:
    match = CAPTURE_RE.search(name)
    if not match:
        return fallback
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return fallback


def parse_frame(path: Path) -> FrameRef | None:
    parsed = parse_frame_name(path.name)
    if parsed is None or not path.is_file():
        return None
    period, bucket, stamp = parsed
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return FrameRef(path=path, period=period, bucket=bucket, stamp=stamp, size=size)


def list_frames(outbox: Path) -> list[FrameRef]:
    if not outbox.is_dir():
        return []
    found: list[FrameRef] = []
    for path in outbox.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        frame = parse_frame(path)
        if frame is not None:
            found.append(frame)
    return found


def choose_deletions(
    frames: list[FrameRef],
    max_bytes: int,
    *,
    night_priority: bool = True,
) -> list[FrameRef]:
    """Oldest day frames go first when night frames have priority.

    max_bytes <= 0 disables the cap.
    """
    if max_bytes <= 0:
        return []
    total = sum(frame.size for frame in frames)
    if total <= max_bytes:
        return []
    if night_priority:
        order = sorted(frames, key=lambda frame: (frame.night, frame.stamp, frame.name))
    else:
        order = sorted(frames, key=lambda frame: (frame.stamp, frame.name))
    victims: list[FrameRef] = []
    for frame in order:
        if total <= max_bytes:
            break
        victims.append(frame)
        total -= frame.size
    return victims


def cap_warning(victims: list[FrameRef]) -> str:
    if not victims:
        return ""
    nights = sum(1 for frame in victims if frame.night)
    days = len(victims) - nights
    return (
        f"outbox over cap: deleting {len(victims)} oldest file(s) "
        f"({days} day, {nights} night)"
    )


def upload_plan(
    frames: list[FrameRef],
    *,
    night_priority: bool,
    drop_day_frames: bool,
) -> tuple[list[FrameRef], list[FrameRef], list[FrameRef]]:
    """Return (first_batch, second_batch, drop_locally).

    With night priority the first batch is night frames and the second is day
    frames, so a short connection spends its time on meteors. Dropped day
    frames are not uploaded.
    """
    night = sorted((frame for frame in frames if frame.night), key=lambda frame: frame.stamp)
    day = sorted((frame for frame in frames if not frame.night), key=lambda frame: frame.stamp)
    if drop_day_frames:
        return night, [], day
    if night_priority:
        return night, day, []
    combined = sorted(night + day, key=lambda frame: frame.stamp)
    return combined, [], []

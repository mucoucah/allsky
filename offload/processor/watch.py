"""Watch the incoming directory and decide what to do with each frame."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from offload.frames import FrameRef, parse_frame


def snapshot_sizes(directory: Path) -> dict[str, int]:
    sizes: dict[str, int] = {}
    if not directory.is_dir():
        return sizes
    for path in directory.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in (".jpg", ".jpeg"):
            continue
        try:
            sizes[path.name] = path.stat().st_size
        except OSError:
            continue
    return sizes


def ready_names(previous: dict[str, int], current: dict[str, int]) -> list[str]:
    """A file is ready when its size is unchanged and non-zero across two scans.

    rsync --partial keeps an unfinished JPEG growing, so a stable size means
    the transfer of that file finished.
    """
    ready: list[str] = []
    for name, size in current.items():
        if size <= 0 or name.startswith("."):
            continue
        if previous.get(name) == size:
            ready.append(name)
    return ready


def dispatch_order(frames: list[FrameRef], *, night_priority: bool = True) -> list[FrameRef]:
    if night_priority:
        return sorted(frames, key=lambda frame: (not frame.night, frame.stamp, frame.name))
    return sorted(frames, key=lambda frame: (frame.stamp, frame.name))


@dataclass
class NightBook:
    last_stamp: str
    last_epoch: float
    saw_day_after: bool = False


@dataclass
class BookState:
    finalized: set[str] = field(default_factory=set)
    open_nights: dict[str, NightBook] = field(default_factory=dict)
    newest_day_stamp: str | None = None

    def note(self, frame: FrameRef, epoch: float) -> None:
        if frame.night:
            book = self.open_nights.get(frame.bucket)
            if book is None or frame.stamp >= book.last_stamp:
                self.open_nights[frame.bucket] = NightBook(
                    last_stamp=frame.stamp,
                    last_epoch=epoch,
                    saw_day_after=book.saw_day_after if book else False,
                )
            return
        if self.newest_day_stamp is None or frame.stamp > self.newest_day_stamp:
            self.newest_day_stamp = frame.stamp
        for book in self.open_nights.values():
            if frame.stamp > book.last_stamp:
                book.saw_day_after = True


def due_nights(
    state: BookState,
    now_epoch: float,
    *,
    quiet_with_day_seconds: int,
    quiet_alone_seconds: int,
) -> list[str]:
    """Nights ready for keogram, startrails, and timelapse.

    A newer night date closes the previous one immediately. Otherwise wait
    until day frames arrive and a short quiet passes, or a longer quiet if
    day frames were dropped on the Pi.
    """
    dates = sorted(state.open_nights)
    due: list[str] = []
    for index, date in enumerate(dates):
        if date in state.finalized:
            continue
        book = state.open_nights[date]
        later = index < len(dates) - 1
        quiet = now_epoch - book.last_epoch
        if later:
            due.append(date)
            continue
        if book.saw_day_after and quiet >= quiet_with_day_seconds:
            due.append(date)
        elif not book.saw_day_after and quiet >= quiet_alone_seconds:
            due.append(date)
    return due


def load_ready(directory: Path, names: list[str]) -> list[FrameRef]:
    frames: list[FrameRef] = []
    for name in names:
        frame = parse_frame(directory / name)
        if frame is not None:
            frames.append(frame)
    return frames

"""Raw-frame retention.

Age and the disk budget select day directories. Inside those directories only
raw frames and their per-frame sidecars/thumbnails are removed. Timelapse
videos, keograms, startrails, meteor hit images/crops/metadata, and anything
under a meteor or hits directory are kept. A day directory that still holds
kept products is left in place.

The walk is a timed scan. It does not use inotify, and it does not create
hardlinks or symlinks (drvfs / 9p cannot be relied on for either).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("allsky-processor")

DATE_RE = re.compile(r"^\d{8}$")
# Offload names (N_/D_) and upstream Allsky names (image-<YYYYMMDDHHMMSS>).
RAW_FRAME_RE = re.compile(
    r"^(?:"
    r"[ND]_\d{8}_\d{8}_\d{6}(?:_\d+)?"
    r"|image-\d{14}(?:_\d+)?"
    r")\.(?:jpe?g|png)$",
    re.IGNORECASE,
)
PRODUCT_NAME_RE = re.compile(
    r"^(?:keogram(?:-|\.)|startrails(?:-|\.)|startrail(?:-|\.)|"
    r"allsky-|mini-timelapse|meteor_|timelapse)",
    re.IGNORECASE,
)
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
SIDECAR_SUFFIXES = {".json", ".txt", ".xml", ".xmp"}
# Directory names that are never entered for deletion.
PROTECTED_DIR_NAMES = {
    "keogram",
    "keograms",
    "startrail",
    "startrails",
    "meteor",
    "meteors",
    "hits",
    "video",
    "videos",
    "timelapse",
    "timelapses",
    "darks",
    "config",
    "tmp",
}
HITS_DIR_NAMES = {"meteor", "meteors", "hits"}


def expired_dates(dates: list[str], today: datetime, keep_days: int) -> list[str]:
    if keep_days < 1:
        return []
    cutoff = (today - timedelta(days=keep_days)).strftime("%Y%m%d")
    return sorted(date for date in dates if date < cutoff)


def dates_over_budget(
    dates_oldest_first: list[str],
    sizes: dict[str, int],
    max_bytes: int,
) -> list[str]:
    """Drop oldest dates until the summed size is within max_bytes.

    max_bytes <= 0 disables the budget. The newest date is kept even if it
    alone is larger than the budget, so tonight is not deleted while it is running.
    """
    if max_bytes <= 0:
        return []
    ordered = list(dates_oldest_first)
    total = sum(sizes.get(date, 0) for date in ordered)
    victims: list[str] = []
    for date in ordered[:-1] if len(ordered) > 1 else []:
        if total <= max_bytes:
            break
        victims.append(date)
        total -= sizes.get(date, 0)
    return victims


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    if path.is_file():
        return path.stat().st_size
    for child in path.rglob("*"):
        if child.is_symlink():
            continue
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def is_raw_frame_name(name: str) -> bool:
    """True for a capture JPEG/PNG sitting directly in a day directory."""
    return RAW_FRAME_RE.match(name) is not None


def _parts_under(path: Path, root: Path) -> tuple[str, ...]:
    """Path components relative to the data root, lowercased.

    Absolute prefixes such as /tmp must not count, or a pytest tree would
    look protected because `tmp` is also the live-image directory name.
    """
    try:
        relative = path.absolute().relative_to(root.absolute())
    except (OSError, ValueError):
        relative = path
    return tuple(part.lower() for part in relative.parts)


def is_protected_path(path: Path, root: Path) -> bool:
    """True when any component under the data root is a product or hits directory."""
    return any(part in PROTECTED_DIR_NAMES for part in _parts_under(path, root))


def _is_hits_path(path: Path, root: Path) -> bool:
    return any(part in HITS_DIR_NAMES for part in _parts_under(path, root))


def _file_size(path: Path) -> int:
    try:
        return path.lstat().st_size
    except OSError:
        return 0


def _stored_under(root: Path, path: Path) -> bool:
    """True when the directory entry itself is under root.

    Symlinks are judged by their path, not the target, so a link can be
    removed without deleting a file that lives outside the data root.
    """
    try:
        path.absolute().relative_to(root.absolute())
    except (OSError, ValueError):
        return False
    return True


@dataclass
class PruneResult:
    removed: list[str] = field(default_factory=list)
    count: int = 0
    bytes: int = 0
    preserved: list[str] = field(default_factory=list)

    def add(self, path: Path, root: Path, size: int) -> None:
        self.removed.append(str(path.relative_to(root)))
        self.count += 1
        self.bytes += size


def _hit_metadata(path: Path) -> bool:
    """JSON that records a meteor hit, as opposed to an exposure sidecar."""
    if path.suffix.lower() != ".json":
        return False
    if path.name.lower().startswith("meteor_"):
        return True
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return "meteor_count" in payload or "lines" in payload


def _doomed_raw_frames(day: Path, data_dir: Path) -> list[Path]:
    """Raw frames directly in a day directory. Product dirs are not entered."""
    if day.is_symlink() or not day.is_dir():
        return []
    found: list[Path] = []
    try:
        children = list(day.iterdir())
    except OSError:
        return []
    for path in children:
        if path.is_symlink():
            if is_raw_frame_name(path.name) and not is_protected_path(path, data_dir):
                found.append(path)
            continue
        if not path.is_file():
            continue
        if is_protected_path(path, data_dir):
            continue
        if path.suffix.lower() in VIDEO_SUFFIXES or PRODUCT_NAME_RE.match(path.name):
            continue
        if _hit_metadata(path):
            continue
        if is_raw_frame_name(path.name):
            found.append(path)
    return found


def _sidecar_and_thumb(frame: Path, data_dir: Path) -> list[Path]:
    """Per-frame sidecar files and the thumbnail that belongs to this frame."""
    extras: list[Path] = []
    day = frame.parent
    try:
        children = list(day.iterdir())
    except OSError:
        return extras
    for path in children:
        if path.name == frame.name:
            continue
        if path.suffix.lower() not in SIDECAR_SUFFIXES or path.stem != frame.stem:
            continue
        if path.is_symlink() or path.is_file():
            if is_protected_path(path, data_dir) or PRODUCT_NAME_RE.match(path.name) or _hit_metadata(path):
                continue
            extras.append(path)
    thumbs = day / "thumbnails"
    if thumbs.is_symlink() or not thumbs.is_dir():
        return extras
    thumb = thumbs / frame.name
    if (thumb.is_symlink() or thumb.is_file()) and not is_protected_path(thumb, data_dir):
        extras.append(thumb)
    return extras


def _hits_destination(json_path: Path, frame: Path, data_dir: Path) -> Path:
    parent = json_path.parent
    if _is_hits_path(parent, data_dir):
        return parent
    return data_dir / "html" / "allsky" / "meteors" / frame.parent.name


def _strings(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _strings(item, out)


def _match_doomed(text: str, doomed: dict[str, list[Path]]) -> list[Path]:
    text = text.strip()
    if not text or len(text) > 1024 or "\n" in text or "\x00" in text:
        return []
    name = Path(text).name
    frames = doomed.get(name)
    if not frames:
        return []
    if text == name:
        return list(frames)
    matched = [frame for frame in frames if frame.parent.name in text or name in text]
    return matched


def _iter_hit_json(data_dir: Path) -> list[Path]:
    found: list[Path] = []
    if not data_dir.is_dir():
        return found
    for path in data_dir.rglob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        if _is_hits_path(path, data_dir) or path.name.lower().startswith("meteor_") or _hit_metadata(path):
            found.append(path)
    return found


def preserve_referenced_frames(
    data_dir: Path,
    doomed: list[Path],
) -> set[Path]:
    """Copy raw frames that hit metadata points at into the hits store.

    Returns frame paths that must not be deleted because the copy failed.
    A hit image that already lives in a meteor/hits directory is not in
    `doomed` and is left untouched.
    """
    by_name: dict[str, list[Path]] = {}
    for frame in doomed:
        by_name.setdefault(frame.name, []).append(frame)
    exclude: set[Path] = set()
    if not by_name:
        return exclude
    copied: set[Path] = set()
    for meta in _iter_hit_json(data_dir):
        try:
            payload = json.loads(meta.read_text())
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        texts: list[str] = []
        _strings(payload, texts)
        for text in texts:
            for frame in _match_doomed(text, by_name):
                if frame in copied or frame in exclude:
                    continue
                if not _stored_under(data_dir, frame):
                    exclude.add(frame)
                    continue
                if _is_hits_path(frame, data_dir):
                    exclude.add(frame)
                    continue
                dest_dir = _hits_destination(meta, frame, data_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / frame.name
                try:
                    if dest.exists() and dest.samefile(frame):
                        exclude.add(frame)
                        continue
                except OSError:
                    pass
                if not dest.exists():
                    try:
                        shutil.copy2(frame, dest, follow_symlinks=True)
                    except OSError:
                        log.warning("raw retention could not preserve %s", frame)
                        exclude.add(frame)
                        continue
                copied.add(frame)
                log.info("raw retention preserved meteor frame %s -> %s", frame, dest)
    return exclude


def _unlink(path: Path) -> None:
    path.unlink()


def _cleanup_day(day: Path) -> None:
    """Drop an emptied thumbnail directory, then a day directory with nothing left."""
    thumbs = day / "thumbnails"
    try:
        if thumbs.is_dir() and not thumbs.is_symlink() and not any(thumbs.iterdir()):
            thumbs.rmdir()
    except OSError:
        pass
    try:
        if day.is_dir() and not day.is_symlink() and not any(day.iterdir()):
            day.rmdir()
    except OSError:
        pass


def prune_raw_frames(
    data_dir: Path,
    *,
    today: datetime,
    keep_days: int,
    extra_dates: list[str] | None = None,
) -> PruneResult:
    """Delete raw frames in day directories older than keep_days, plus extra_dates.

    keep_days < 1 disables the age rule. extra_dates is how the disk budget
    selects older nights without waiting for the age cutoff. Nothing under a
    protected directory is deleted. Referenced meteor frames are copied into
    the hits store first; if that copy fails the original frame is kept.
    """
    result = PruneResult()
    images = data_dir / "images"
    if not images.is_dir():
        return result
    try:
        day_names = sorted(
            path.name
            for path in images.iterdir()
            if path.is_dir() and not path.is_symlink() and DATE_RE.match(path.name)
        )
    except OSError:
        return result
    selected = set(expired_dates(day_names, today, keep_days))
    for date in extra_dates or []:
        if DATE_RE.match(date):
            selected.add(date)
    if not selected:
        return result

    doomed: list[Path] = []
    for date in sorted(selected):
        day = images / date
        doomed.extend(_doomed_raw_frames(day, data_dir))
    exclude = preserve_referenced_frames(data_dir, doomed)

    for frame in doomed:
        if frame in exclude:
            continue
        if not frame.exists() and not frame.is_symlink():
            continue
        companions = _sidecar_and_thumb(frame, data_dir)
        for path in [frame, *companions]:
            if path in exclude:
                continue
            if not path.exists() and not path.is_symlink():
                continue
            size = _file_size(path)
            try:
                _unlink(path)
            except OSError:
                log.warning("raw retention could not remove %s", path)
                continue
            result.add(path, data_dir, size)
    for date in sorted(selected):
        day = images / date
        if day.is_dir() and not day.is_symlink():
            _cleanup_day(day)
    if result.count:
        log.info("raw retention removed %d file(s), %d bytes", result.count, result.bytes)
    return result

"""Image discovery + EXIF extraction for the gallery.

The on-disk source of truth is ${ALLSKY_HOME}/images/YYYYMMDD/. We mirror that
into a SQLite index for fast filtering & sorting; the indexer is incremental and
debounced via mtimes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from PIL import ExifTags, Image, UnidentifiedImageError

from .paths import paths

DATE_DIR_RE = re.compile(r"^20\d{2}[01]\d[0-3]\d$")
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

# A handful of EXIF tags we care about for sorting/filtering.
_INTERESTING_TAGS = {
    "DateTimeOriginal",
    "ExposureTime",
    "ISOSpeedRatings",
    "FNumber",
    "ImageWidth",
    "ImageLength",
}


@dataclass
class ImageRecord:
    path: str          # path relative to ALLSKY_HOME (stable across mounts)
    date_dir: str      # YYYYMMDD
    filename: str
    captured_at: float  # mtime epoch seconds (we trust mtime; EXIF often missing)
    size_bytes: int
    width: int | None
    height: int | None
    exposure_us: int | None  # microseconds
    iso: int | None
    has_thumbnail: bool


def list_date_dirs() -> list[str]:
    base = paths().images
    if not base.exists():
        return []
    return sorted(
        (p.name for p in base.iterdir() if p.is_dir() and DATE_DIR_RE.match(p.name)),
        reverse=True,
    )


def iter_day(date_dir: str) -> Iterator[Path]:
    d = paths().day_dir(date_dir)
    if not d.exists():
        return iter(())
    return (
        p
        for p in sorted(d.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
    )


def thumbnail_for(image_path: Path) -> Path | None:
    """Allsky stores thumbnails alongside originals in a `thumbnails/` subdir."""
    cand = image_path.parent / "thumbnails" / image_path.name
    return cand if cand.exists() else None


def _exposure_to_us(value) -> int | None:
    """Pillow returns ExposureTime as a Fraction-like; coerce to microseconds."""
    if value is None:
        return None
    try:
        return int(round(float(value) * 1_000_000))
    except (TypeError, ValueError):
        try:
            num, den = value
            return int(round((num / den) * 1_000_000))
        except Exception:
            return None


def extract_exif(p: Path) -> dict:
    """Pull a tiny set of EXIF tags. Designed to never raise on the indexer."""
    out: dict = {}
    try:
        with Image.open(p) as img:
            out["width"], out["height"] = img.size
            raw = img._getexif() or {}
            for tag_id, value in raw.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                if tag in _INTERESTING_TAGS:
                    out[tag] = value
    except (UnidentifiedImageError, OSError, AttributeError):
        pass
    return out


def scan_to_records(date_dir: str) -> Iterator[ImageRecord]:
    home = paths().home
    for p in iter_day(date_dir):
        try:
            st = p.stat()
        except OSError:
            continue
        exif = extract_exif(p)
        yield ImageRecord(
            path=str(p.relative_to(home)),
            date_dir=date_dir,
            filename=p.name,
            captured_at=st.st_mtime,
            size_bytes=st.st_size,
            width=exif.get("width"),
            height=exif.get("height"),
            exposure_us=_exposure_to_us(exif.get("ExposureTime")),
            iso=int(exif.get("ISOSpeedRatings")) if exif.get("ISOSpeedRatings") else None,
            has_thumbnail=thumbnail_for(p) is not None,
        )


def resolve_image(rel_path: str) -> Path | None:
    """Validate a request path stays inside the images dir (no path traversal)."""
    home = paths().home
    candidate = (home / rel_path).resolve()
    try:
        candidate.relative_to(paths().images.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def captured_iso(rec_mtime: float) -> str:
    return datetime.fromtimestamp(rec_mtime).isoformat(timespec="seconds")

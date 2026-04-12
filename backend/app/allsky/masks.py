"""Mask file management.

Allsky's allsky_maskimage.py module reads grayscale PNGs from
${ALLSKY_HOME}/config/overlay/images/<name>. Our editor writes them there
directly — no extra integration needed. We require the dimensions to match the
current frame so the upstream module accepts them.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable

from PIL import Image

from .paths import paths


def list_masks() -> list[dict]:
    d = paths().masks_dir
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".png":
            continue
        try:
            with Image.open(p) as img:
                w, h = img.size
            out.append(
                {
                    "name": p.name,
                    "width": w,
                    "height": h,
                    "size_bytes": p.stat().st_size,
                }
            )
        except (OSError, ValueError):
            continue
    return out


def read_mask(name: str) -> Path | None:
    d = paths().masks_dir.resolve()
    p = (d / name).resolve()
    try:
        p.relative_to(d)
    except ValueError:
        return None
    return p if p.exists() else None


def latest_image_dimensions() -> tuple[int, int] | None:
    p = paths().latest_image
    if not p.exists():
        return None
    try:
        with Image.open(p) as img:
            return img.size
    except (OSError, ValueError):
        return None


def write_mask(name: str, png_bytes: bytes) -> dict:
    """Atomically write a PNG mask. Returns a metadata dict on success.

    Raises ValueError on validation issues so the router can return 4xx.
    """
    if not name.endswith(".png") or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("mask name must be a plain *.png filename")

    d = paths().masks_dir
    d.mkdir(parents=True, exist_ok=True)
    target = d / name

    # Sanity-check the PNG.
    tmp_dir = d
    fd, tmp_name = tempfile.mkstemp(prefix=".mask-", suffix=".png", dir=tmp_dir)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(png_bytes)
        with Image.open(tmp_name) as img:
            img.verify()
        with Image.open(tmp_name) as img:
            w, h = img.size
            mode = img.mode
        # Coerce to single-channel L mode if needed; the upstream module loads with
        # cv2.IMREAD_GRAYSCALE so technically it doesn't matter, but a clean L mode
        # mask is more predictable for users.
        if mode != "L":
            with Image.open(tmp_name) as img:
                img.convert("L").save(tmp_name, "PNG")

        latest = latest_image_dimensions()
        if latest and (w, h) != latest:
            raise ValueError(
                f"mask size {w}x{h} does not match current frame {latest[0]}x{latest[1]}"
            )

        os.replace(tmp_name, target)
        tmp_name = ""  # consumed
        return {"name": name, "width": w, "height": h, "size_bytes": target.stat().st_size}
    finally:
        if tmp_name and Path(tmp_name).exists():
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def delete_mask(name: str) -> bool:
    p = read_mask(name)
    if not p:
        return False
    try:
        p.unlink()
        return True
    except OSError:
        return False

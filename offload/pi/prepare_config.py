#!/usr/bin/env python3
"""Build the config directory a light (capture-only) Pi needs.

The capture binary does not read settings.json itself. allsky.sh runs
convertJSON.py --capture-only, which emits a setting only when options.json
marks it usage=capture. Without that schema, latitude and longitude are
dropped and capture_RPi exits with "not specified".

This writes the same files the full install copies for the capture path,
fills settings.json with schema defaults, and keeps the caller's latitude,
longitude, angle, and camera model. The settings hardlink is named from the
final model so allsky.sh does not relink on the next start.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

# Same numbers as backend/app/allsky/settings.py PLACEHOLDER_DEFAULTS.
# options.json stores sentinels ("night_default", "_default") that the capture
# binary cannot parse. Resolved here so a light install does not need the web UI.
PLACEHOLDER_DEFAULTS: dict[str, Any] = {
    "daymean": 0.5,
    "nightmean": 0.2,
    "daymeanthreshold": 0.1,
    "nightmeanthreshold": 0.1,
    "dayautogain": True,
    "nightautogain": True,
    "daymaxautoexposure": 10_000,
    "nightmaxautoexposure": 10_000,
    "daymaxautogain": 10,
    "nightmaxautogain": 29,
    "dayexposure": 300,
    "nightexposure": 8_000,
    "daygain": 1,
    "nightgain": 16,
    "daydelay": 10_000,
    "nightdelay": 500,
    "thumbnailsizex": 100,
    "thumbnailsizey": 75,
    "daywbr": 2.5,
    "daywbb": 2.0,
    "nightwbr": 2.5,
    "nightwbb": 2.0,
    "saturation": 1.0,
    "contrast": 1.0,
    "sharpness": 1.0,
    "aggression": 75,
    "gaintransitiontime": 5,
    "daytargettemp": 0,
    "nighttargettemp": -5,
    "usb": 40,
    "daystretchmidpoint": 10,
    "nightstretchmidpoint": 10,
    "imagecroptop": 0,
    "imagecropbottom": 0,
    "imagecropleft": 0,
    "imagecropright": 0,
    "imageresizeuploadswidth": 0,
    "imageresizeuploadsheight": 0,
    "timelapsewidth": 1920,
    "timelapseheight": 0,
    "minitimelapsewidth": 0,
    "minitimelapseheight": 0,
}

_SENSOR_ALIASES = {"imx462": "imx290"}


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return (
        value in {"_min", "_max", "_default"}
        or value.endswith("_default")
        or value.endswith("_min")
        or value.endswith("_max")
    )


def _coerce(value: Any, otype: str) -> Any:
    if otype == "boolean":
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes"}
        return bool(value)
    if otype in {"integer", "select_integer"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if otype in {"float", "percent"}:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def resolve_default(name: str, raw: Any, otype: str) -> Any:
    if _is_placeholder(raw) or raw is None:
        if name in PLACEHOLDER_DEFAULTS:
            return PLACEHOLDER_DEFAULTS[name]
        if otype == "boolean":
            return False
        if otype in {"integer", "select_integer", "float", "percent"}:
            return 0
        return ""
    return _coerce(raw, otype)


def canonical_model(model: str, camera_info: str) -> str:
    """Map a bare sensor name to the catalog model. Keep strings that already have a space."""
    text = (model or "").strip()
    if not text or " " in text:
        return text
    lookup = _SENSOR_ALIASES.get(text, text)
    for line in camera_info.splitlines():
        if not line.startswith("camera\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 4 and parts[1].strip() == lookup:
            return parts[3].strip()
    return text


def settings_link_name(camera_type: str, model: str) -> str:
    safe = (model or "unknown").replace(" ", "_").replace("/", "_")
    return f"settings_{camera_type}_{safe}.json"


def schema_defaults(options: list[dict]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for entry in options:
        name = entry.get("name") or ""
        otype = str(entry.get("type") or "")
        if not name or otype.startswith("header"):
            continue
        merged[name] = resolve_default(name, entry.get("default"), otype)
    return merged


def merge_settings(existing: dict[str, Any], options: list[dict], camera_info: str) -> dict[str, Any]:
    merged = schema_defaults(options)
    for key, value in existing.items():
        if _is_placeholder(value):
            continue
        merged[key] = value
    for bad in ("contrast", "sharpness"):
        try:
            if float(merged.get(bad, 1)) == 0.0:
                merged[bad] = 1.0
        except (TypeError, ValueError):
            pass
    if not str(merged.get("cameratype") or "").strip():
        merged["cameratype"] = "RPi"
    model = str(merged.get("cameramodel") or "").strip() or "imx290"
    merged["cameramodel"] = canonical_model(model, camera_info)
    merged["cameranumber"] = str(merged.get("cameranumber", "0"))
    if not str(merged.get("lastchanged") or "").strip():
        merged["lastchanged"] = "1"
    if not str(merged.get("filename") or "").strip():
        merged["filename"] = "image.jpg"
    return merged


def relink_settings(settings_path: Path, camera_type: str, model: str) -> Path:
    """Hardlink settings.json to settings_<type>_<model>.json and drop stale names."""
    link = settings_path.with_name(settings_link_name(camera_type, model))
    inode = settings_path.stat().st_ino
    if link.exists() and link.stat().st_ino != inode:
        link.unlink()
    if not link.exists():
        os.link(settings_path, link)
    prefix = f"settings_{camera_type}_"
    for other in settings_path.parent.glob(f"{prefix}*.json"):
        if other.name == link.name:
            continue
        try:
            same = other.stat().st_ino == inode and other.stat().st_dev == settings_path.stat().st_dev
        except OSError:
            continue
        if same:
            other.unlink()
    return link


def _copy_repo(home: Path, name: str, *, always: bool) -> None:
    src = home / "config_repo" / f"{name}.repo"
    dest = home / "config" / name
    if not src.is_file():
        return
    if always or not dest.exists():
        shutil.copyfile(src, dest)


def prepare(home: Path) -> dict[str, str]:
    home = home.resolve()
    config = home / "config"
    config.mkdir(parents=True, exist_ok=True)
    _copy_repo(home, "options.json", always=True)
    _copy_repo(home, "RPi_cameraInfo.txt", always=True)
    _copy_repo(home, "env.json", always=False)
    _copy_repo(home, "autoexposure.json", always=False)

    options_path = config / "options.json"
    info_path = config / "RPi_cameraInfo.txt"
    settings_path = config / "settings.json"
    options = json.loads(options_path.read_text()) if options_path.is_file() else []
    camera_info = info_path.read_text() if info_path.is_file() else ""
    existing: dict[str, Any] = {}
    if settings_path.is_file():
        existing = json.loads(settings_path.read_text())
    merged = merge_settings(existing, options, camera_info)
    settings_path.write_text(json.dumps(merged, indent=4) + "\n")
    link = relink_settings(settings_path, str(merged["cameratype"]), str(merged["cameramodel"]))
    return {
        "settings": str(settings_path),
        "link": str(link),
        "cameramodel": str(merged["cameramodel"]),
        "cameratype": str(merged["cameratype"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Allsky light-client config")
    parser.add_argument("--home", required=True, help="ALLSKY_HOME")
    args = parser.parse_args(argv)
    result = prepare(Path(args.home))
    print(
        f"    cameramodel={result['cameramodel']} "
        f"link={Path(result['link']).name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

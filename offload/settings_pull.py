"""Pull camera settings the PC wrote and install them on the Pi."""
from __future__ import annotations

import json
import os
from pathlib import Path

from offload.config import OffloadConfig, load_config, merge_push, save_config


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def apply_pulled(staging: Path, settings_dest: Path, offload_file: Path | None) -> bool:
    """Return True when capture should restart because settings changed."""
    changed = False
    remote_settings = staging / "settings.json"
    if remote_settings.is_file():
        new = remote_settings.read_bytes()
        old = settings_dest.read_bytes() if settings_dest.is_file() else b""
        if new.strip() and new != old:
            _atomic_write(settings_dest, new)
            changed = True
    push_file = staging / "offload-push.json"
    if push_file.is_file() and offload_file is not None:
        try:
            pushed = json.loads(push_file.read_text())
        except (OSError, json.JSONDecodeError):
            pushed = None
        if isinstance(pushed, dict):
            cfg = load_config(offload_file)
            cfg, push_changed = merge_push(cfg, pushed)
            if push_changed:
                save_config(cfg, offload_file)
                changed = True
    return changed


def settings_destination(cfg: OffloadConfig | None = None) -> Path:
    home = os.environ.get("ALLSKY_HOME", "")
    if not home:
        raise OSError("ALLSKY_HOME is not set")
    return Path(home) / "config" / "settings.json"

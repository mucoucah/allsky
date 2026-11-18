"""Stop storing raw frames when the data drive is low on space.

The check uses shutil.disk_usage on the data root before each ingest. It does
not watch the directory with inotify. Meteor detection, meteor hits, and the
live image keep updating while the guard is active. Incoming frames are
deleted after that work so the Pi outbox does not fill up.

The guard trips below min_free_gb and clears only after free space is at
least min_free_gb + 2 GB, so it does not flap around the threshold.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

GB = 1024 ** 3
HYSTERESIS_GB = 2.0


def disk_free_gb(path: Path) -> float | None:
    """Free space on the filesystem that holds path, in GiB (1024**3)."""
    target = path if path.exists() else path.parent
    if not target.exists():
        target = Path("/")
    try:
        return shutil.disk_usage(target).free / GB
    except OSError:
        return None


def guard_is_active(was_active: bool, free_gb: float | None, min_free_gb: float) -> bool:
    """Next guard state. min_free_gb <= 0 disables the guard.

    A missing measurement keeps the previous state so a transient stat
    failure does not drop frames or clear an active guard.
    """
    if min_free_gb <= 0:
        return False
    if free_gb is None:
        return was_active
    if was_active:
        return free_gb < (min_free_gb + HYSTERESIS_GB)
    return free_gb < min_free_gb


def guard_timestamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")

"""Decide whether a path can be watched with inotify.

WSL drvfs (9p) does not deliver inotify events for the Windows drive the
data root is moving onto. Callers poll those paths instead.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from watchfiles import awatch

_POLL_TYPES = {"9p", "drvfs"}


def filesystem_type(path: Path, mounts: str | None = None) -> str:
    """Return the /proc/mounts fstype of the longest mount covering path."""
    try:
        target = path if path.exists() else path.parent
        resolved = str(target.resolve())
    except OSError:
        return ""
    if mounts is None:
        try:
            mounts = Path("/proc/mounts").read_text()
        except OSError:
            return ""
    best = ""
    fstype = ""
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount = parts[1].replace("\\040", " ")
        typ = parts[2]
        covered = resolved == mount or resolved.startswith(mount.rstrip("/") + "/")
        if covered and len(mount) >= len(best):
            best = mount
            fstype = typ
    return fstype


def needs_poll(path: Path, mounts: str | None = None) -> bool:
    """True when inotify will not see changes under path."""
    return filesystem_type(path, mounts).lower() in _POLL_TYPES


def watch_directory(path: Path, **kwargs):
    """awatch, polling when the filesystem will not emit inotify events."""
    kwargs["force_polling"] = kwargs.get("force_polling", needs_poll(path))
    kwargs.setdefault("poll_delay_ms", 1000)
    accepted = inspect.signature(awatch).parameters
    filtered = {key: value for key, value in kwargs.items() if key in accepted}
    return awatch(path, **filtered)

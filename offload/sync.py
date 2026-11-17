"""rsync command lines, retry backoff, and delete-after-confirm.

The agent deletes a local frame only after the transfer of that file is
confirmed. rsync --remove-source-files does that itself; a failed run leaves
the remaining files in the outbox for the next attempt. --partial and
--append-verify keep a dropped Wi-Fi transfer resumable.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from offload.config import OffloadConfig, RemoteConfig
from offload.frames import FrameRef, cap_warning, choose_deletions, list_frames, upload_plan


def backoff_seconds(attempt: int, base: float = 5.0, cap: float = 300.0) -> float:
    """attempt 1 -> base, then doubles, never above cap."""
    step = max(1, int(attempt))
    return float(min(cap, base * (2 ** (step - 1))))


def bandwidth_kib_per_s(kbps: int) -> int:
    """rsync --bwlimit is KiB/s. The config value is kilobits/s. 0 means off."""
    if kbps <= 0:
        return 0
    return max(1, int(kbps) // 8)


def ssh_shell(remote: RemoteConfig) -> str:
    parts = [
        "ssh",
        "-p", str(int(remote.port)),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    key = (remote.ssh_key or "").strip()
    if key:
        parts[1:1] = ["-i", key]
    return " ".join(shlex.quote(part) for part in parts)


def _remote_target(remote: RemoteConfig, relative: str = "") -> str:
    host = remote.host.strip()
    user = remote.user.strip()
    path = remote.path.rstrip("/")
    if relative:
        path = f"{path}/{relative.lstrip('/')}"
    login = f"{user}@{host}" if user else host
    return f"{login}:{path}"


def build_rsync_upload(
    remote: RemoteConfig,
    list_file: Path,
    *,
    remove_source: bool,
) -> list[str]:
    cmd = [
        "rsync",
        "-rt",
        "--partial",
        "--append-verify",
        "--timeout=60",
        "--files-from", str(list_file),
        "-e", ssh_shell(remote),
    ]
    limit = bandwidth_kib_per_s(remote.bandwidth_limit_kbps)
    if limit:
        cmd.extend(["--bwlimit", str(limit)])
    if remove_source:
        cmd.append("--remove-source-files")
    cmd.append("./")
    cmd.append(_remote_target(remote) + "/")
    return cmd


def build_rsync_status(remote: RemoteConfig, local_status: Path, relative: str | None = None) -> list[str]:
    """Upload one small file. The local copy is kept."""
    rel = remote.status_name if relative is None else relative
    return [
        "rsync",
        "-t",
        "--partial",
        "--timeout=30",
        "-e", ssh_shell(remote),
        str(local_status),
        _remote_target(remote, rel),
    ]


def build_rsync_pull(remote: RemoteConfig, local_dir: Path) -> list[str]:
    source = remote.settings_path.rstrip("/") + "/"
    host = remote.host.strip()
    user = remote.user.strip()
    login = f"{user}@{host}" if user else host
    return [
        "rsync",
        "-rt",
        "--partial",
        "--timeout=30",
        "-e", ssh_shell(remote),
        f"{login}:{source}",
        str(local_dir) + "/",
    ]


def apply_confirmed(frames: list[FrameRef], confirmed: set[str], *, ok: bool) -> list[str]:
    """Unlink local frames that the transfer confirmed. A failed batch deletes nothing."""
    if not ok:
        return []
    removed: list[str] = []
    for frame in frames:
        if frame.name not in confirmed:
            continue
        try:
            if frame.path.is_file():
                frame.path.unlink()
                removed.append(frame.name)
        except OSError:
            continue
    return removed


@dataclass
class CycleResult:
    ok: bool
    warning: str = ""
    uploaded_night: list[str] = field(default_factory=list)
    uploaded_day: list[str] = field(default_factory=list)
    dropped_day: list[str] = field(default_factory=list)
    capped: list[str] = field(default_factory=list)
    settings_changed: bool = False
    error: str = ""


class TransferRunner:
    """What a cycle needs from the network. Tests supply a fake."""

    def upload(self, frames: list[FrameRef], *, remove_source: bool) -> bool:
        raise NotImplementedError

    def upload_status(self, path: Path) -> bool:
        raise NotImplementedError

    def pull(self, dest: Path) -> bool:
        raise NotImplementedError


def enforce_cap(outbox: Path, cfg: OffloadConfig) -> tuple[list[str], str]:
    frames = list_frames(outbox)
    victims = choose_deletions(
        frames,
        cfg.outbox_max_bytes,
        night_priority=cfg.night_priority,
    )
    warning = cap_warning(victims)
    removed: list[str] = []
    for frame in victims:
        try:
            frame.path.unlink()
            removed.append(frame.name)
        except OSError:
            continue
    return removed, warning


def cycle(cfg: OffloadConfig, outbox: Path, runner: TransferRunner, status_file: Path) -> CycleResult:
    """One sync attempt: cap, heartbeat, night frames, then day frames, then pull settings."""
    result = CycleResult(ok=True)
    capped, warning = enforce_cap(outbox, cfg)
    result.capped = capped
    result.warning = warning
    status_ok = True
    if status_file.is_file():
        status_ok = runner.upload_status(status_file)
    frames = list_frames(outbox)
    first, second, drop = upload_plan(
        frames,
        night_priority=cfg.night_priority,
        drop_day_frames=cfg.drop_day_frames,
    )
    for frame in drop:
        try:
            frame.path.unlink()
            result.dropped_day.append(frame.name)
        except OSError:
            continue
    if first and not runner.upload(first, remove_source=True):
        result.ok = False
        result.error = "frame upload failed"
        return result
    result.uploaded_night = [frame.name for frame in first if frame.night]
    result.uploaded_day = [frame.name for frame in first if not frame.night]
    if second and not runner.upload(second, remove_source=True):
        result.ok = False
        result.error = "day frame upload failed"
        return result
    result.uploaded_day.extend(frame.name for frame in second)
    if not status_ok and not result.uploaded_night and not result.uploaded_day and not result.dropped_day:
        result.ok = False
        result.error = "status upload failed"
    return result

"""Low-priority loop: push the outbox to the PC and pull settings back.

Run by allsky-sync.service. A failed transfer sleeps with exponential backoff
and leaves the frames on disk. The PC being off is the normal case.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from offload.config import config_path, load_config
from offload.frames import list_frames
from offload.heartbeat import (
    build_status,
    disk_report,
    last_camera_error,
    read_temp_c,
    read_thermal_state,
    tail_text,
    write_status,
)
from offload.settings_pull import apply_pulled, settings_destination
from offload.sync import (
    CycleResult,
    TransferRunner,
    backoff_seconds,
    build_rsync_pull,
    build_rsync_status,
    build_rsync_upload,
    cycle,
)

log = logging.getLogger("allsky-sync")


def _run(cmd: list[str], cwd: Path | None = None) -> bool:
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("command failed to start: %s", exc)
        return False
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        log.warning("rsync exit %s: %s", completed.returncode, err[-400:])
        return False
    return True


class RsyncRunner(TransferRunner):
    def __init__(self, outbox: Path):
        self.outbox = outbox

    def upload(self, frames, *, remove_source: bool) -> bool:
        if not frames:
            return True
        list_file = self.outbox / ".rsync-files"
        list_file.write_text("".join(f"{frame.name}\n" for frame in frames))
        cfg = load_config()
        cmd = build_rsync_upload(cfg.remote, list_file, remove_source=remove_source)
        ok = _run(cmd, cwd=self.outbox)
        list_file.unlink(missing_ok=True)
        return ok

    def upload_status(self, path: Path) -> bool:
        cfg = load_config()
        if not cfg.remote.host:
            return False
        return _run(build_rsync_status(cfg.remote, path))

    def pull(self, dest: Path) -> bool:
        cfg = load_config()
        if not cfg.remote.host or not cfg.remote.settings_path:
            return False
        dest.mkdir(parents=True, exist_ok=True)
        return _run(build_rsync_pull(cfg.remote, dest))


def _last_frame(outbox: Path) -> tuple[str | None, str | None]:
    state = outbox.parent / "last_frame.json"
    try:
        data = json.loads(state.read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    if isinstance(data, dict) and data.get("time"):
        return str(data.get("time")), data.get("name")
    frames = list_frames(outbox)
    if not frames:
        return None, None
    newest = max(frames, key=lambda frame: frame.stamp)
    return newest.stamp, newest.name


def _camera_error(home: Path) -> str | None:
    chunks = []
    for path in (
        home / "tmp" / "capture_RPi_debug.txt",
        Path("/var/log/allsky.log"),
    ):
        chunks.append(tail_text(path))
    return last_camera_error("\n".join(chunks))


def _throttled_text() -> str | None:
    try:
        completed = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or "") + (completed.stderr or "")
    return text.strip() or None


def write_heartbeat(home: Path, outbox: Path) -> Path:
    cfg = load_config()
    frames = list_frames(outbox)
    last_time, last_name = _last_frame(outbox)
    status = build_status(
        temp_c=read_temp_c(),
        throttled_text=_throttled_text(),
        disk=disk_report(outbox if outbox.exists() else home),
        outbox_bytes=sum(frame.size for frame in frames),
        outbox_files=len(frames),
        last_frame_time=last_time,
        last_frame_name=last_name,
        camera_error=_camera_error(home),
        thermal_state=read_thermal_state(home / "tmp"),
        mode=cfg.mode,
    )
    path = outbox.parent / "pi-status.json"
    write_status(path, status)
    return path


def restart_capture() -> None:
    subprocess.run(
        ["sudo", "-n", "/usr/bin/systemctl", "restart", "allsky.service"],
        check=False,
        timeout=30,
    )


def one_cycle() -> CycleResult:
    cfg = load_config()
    home = Path(os.environ.get("ALLSKY_HOME", "."))
    outbox = Path(cfg.outbox_dir)
    outbox.mkdir(parents=True, exist_ok=True)
    status = write_heartbeat(home, outbox)
    if not cfg.capture_only:
        return CycleResult(ok=True, error="mode is normal")
    if not cfg.remote.host:
        return CycleResult(ok=False, error="remote.host is empty")
    mask = home / "config" / "overlay" / "images" / "mask.png"
    if mask.is_file():
        _run(build_rsync_status(cfg.remote, mask, "mask.png"))
    runner = RsyncRunner(outbox)
    result = cycle(cfg, outbox, runner, status)
    if not result.ok:
        return result
    staging = outbox.parent / "from-pc"
    if runner.pull(staging):
        try:
            changed = apply_pulled(staging, settings_destination(), config_path())
        except OSError as exc:
            log.warning("settings pull apply failed: %s", exc)
            changed = False
        result.settings_changed = changed
        if changed:
            log.info("camera settings changed; restarting capture")
            restart_capture()
    else:
        log.info("settings pull skipped or failed; frames already sent stay sent")
    if result.warning:
        log.warning(result.warning)
    return result


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    attempt = 0
    while True:
        cfg = load_config()
        if not cfg.capture_only:
            log.info("mode is normal; sync agent idle")
            time.sleep(60)
            attempt = 0
            continue
        result = one_cycle()
        if result.ok:
            attempt = 0
            log.info(
                "sync ok night=%d day=%d dropped=%d capped=%d",
                len(result.uploaded_night),
                len(result.uploaded_day),
                len(result.dropped_day),
                len(result.capped),
            )
            time.sleep(15)
        else:
            attempt += 1
            delay = backoff_seconds(attempt)
            log.warning("sync failed (%s); retry in %.0fs", result.error, delay)
            time.sleep(delay)


if __name__ == "__main__":
    sys.exit(main())

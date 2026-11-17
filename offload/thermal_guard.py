"""Standalone thermal guard for the light client.

The full install runs the same rules inside the web process. This process
exists so a Pi with no web UI still lengthens the capture delay when warm
and pauses capture when hot. It only needs the Python standard library.
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

from offload.heartbeat import read_temp_c
from offload.thermal_logic import decide_state, format_guard_line, guard_actions

log = logging.getLogger("allsky-thermal")

DEFAULTS = {
    "enabled": True,
    "warn_c": 70.0,
    "stop_c": 80.0,
    "resume_c": 65.0,
    "poll_seconds": 45,
    "warm_extra_delay_ms": 15_000,
}


def load_thermal(home: Path) -> dict:
    cfg = dict(DEFAULTS)
    path = home / "config" / "thermal_config.json"
    data_env = os.environ.get("ALLSKY_WEB_DATA", "")
    candidates = [path]
    if data_env:
        candidates.insert(0, Path(data_env) / "thermal_config.json")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            stored = json.loads(candidate.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(stored, dict):
            for key in DEFAULTS:
                if key in stored:
                    cfg[key] = stored[key]
        break
    cfg["enabled"] = bool(cfg["enabled"])
    for key in ("warn_c", "stop_c", "resume_c"):
        cfg[key] = float(cfg[key])
    cfg["poll_seconds"] = int(cfg["poll_seconds"])
    cfg["warm_extra_delay_ms"] = int(cfg["warm_extra_delay_ms"])
    return cfg


def write_guard(tmp_dir: Path, state: str, extra_ms: int, skip: bool) -> None:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_dir / "thermal_guard"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(format_guard_line(state, extra_ms, skip))
    os.replace(tmp, target)


def _systemctl(verb: str) -> None:
    subprocess.run(
        ["sudo", "-n", "/usr/bin/systemctl", verb, "allsky.service"],
        check=False,
        timeout=30,
    )


def _hold_path(home: Path) -> Path:
    return home / "config" / "thermal_hold.json"


def _hold_active(home: Path) -> bool:
    path = _hold_path(home)
    try:
        return bool(json.loads(path.read_text()).get("capture_stopped_by_us"))
    except (OSError, json.JSONDecodeError):
        return False


def _set_hold(home: Path, active: bool) -> None:
    path = _hold_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"capture_stopped_by_us": active}))
    os.replace(tmp, path)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    home = Path(os.environ.get("ALLSKY_HOME", "."))
    previous = "ok"
    while True:
        cfg = load_thermal(home)
        poll = max(30, min(60, int(cfg["poll_seconds"])))
        try:
            if not cfg["enabled"]:
                write_guard(home / "tmp", "ok", 0, False)
                if _hold_active(home):
                    _systemctl("start")
                    _set_hold(home, False)
                previous = "ok"
            else:
                temp = read_temp_c()
                state = decide_state(
                    previous,
                    temp,
                    warn_c=cfg["warn_c"],
                    stop_c=cfg["stop_c"],
                    resume_c=cfg["resume_c"],
                )
                extra, skip = guard_actions(state, cfg["warm_extra_delay_ms"])
                write_guard(home / "tmp", state, extra, skip)
                if state != previous:
                    shown = f"{temp:.1f}" if temp is not None else "unknown"
                    log.info("thermal %s -> %s at %s C", previous, state, shown)
                if state == "stopped":
                    _set_hold(home, True)
                    _systemctl("stop")
                elif _hold_active(home):
                    _systemctl("start")
                    _set_hold(home, False)
                previous = state
        except Exception:
            log.exception("thermal poll failed")
        time.sleep(poll)


if __name__ == "__main__":
    sys.exit(main())

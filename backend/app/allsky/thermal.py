"""CPU thermal guard for a Pi 4 running long night exposures.

Every poll (default 45 s) this reads /sys/class/thermal/thermal_zone0/temp.
vcgencmd get_throttled is cached and is not called more often than the poll.
Above warn_c (default 70 C) the capture delay is lengthened and non-essential
per-frame work is skipped. Above stop_c (default 80 C) capture is stopped
until the CPU falls to resume_c (default 65 C).

The capture binary and the bash pipeline read ${ALLSKY_TMP}/thermal_guard,
one line: "<state> <extra_delay_ms> <skip_processing>".
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "warn_c": 70.0,
    "stop_c": 80.0,
    "resume_c": 65.0,
    "poll_seconds": 45,
    "warm_extra_delay_ms": 15_000,
}

_LOCK = threading.Lock()
_STATUS: dict[str, Any] = {
    "enabled": True,
    "state": "ok",
    "temp_c": None,
    "warn_c": DEFAULTS["warn_c"],
    "stop_c": DEFAULTS["stop_c"],
    "resume_c": DEFAULTS["resume_c"],
    "poll_seconds": DEFAULTS["poll_seconds"],
    "skip_processing": False,
    "extra_delay_ms": 0,
    "throttled": False,
    "capture_held": False,
    "message": "Thermal guard starting",
}


def decide_state(
    previous: str,
    temp_c: float | None,
    *,
    warn_c: float,
    stop_c: float,
    resume_c: float,
) -> str:
    """Next guard state.

    Once capture is stopped it stays stopped until temp_c <= resume_c.
    A resume that is still at or above warn_c lands on "warm", not "ok".
    """
    if temp_c is None:
        return previous if previous in ("ok", "warm", "stopped") else "ok"
    if previous == "stopped":
        if temp_c > resume_c:
            return "stopped"
        if temp_c >= warn_c:
            return "warm"
        return "ok"
    if temp_c >= stop_c:
        return "stopped"
    if temp_c >= warn_c:
        return "warm"
    return "ok"


def format_guard_line(state: str, extra_delay_ms: int, skip_processing: bool) -> str:
    skip = 1 if skip_processing else 0
    return f"{state} {int(extra_delay_ms)} {skip}\n"


def guard_actions(state: str, warm_extra_delay_ms: int) -> tuple[int, bool]:
    """Extra inter-frame delay (ms) and whether to skip non-essential work."""
    if state == "warm":
        return max(0, int(warm_extra_delay_ms)), True
    if state == "stopped":
        return 0, True
    return 0, False


def skip_nonessential() -> bool:
    """True while overlays, focus/rain watchers, and mini-timelapse should idle."""
    with _LOCK:
        return bool(_STATUS.get("skip_processing"))


def public_status() -> dict[str, Any]:
    with _LOCK:
        return dict(_STATUS)


def _config_path() -> Path:
    return get_settings().data_dir / "thermal_config.json"


def _flag_path() -> Path:
    return get_settings().data_dir / "thermal_hold.json"


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    path = _config_path()
    if path.exists():
        try:
            with path.open() as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                cfg.update({k: stored[k] for k in DEFAULTS if k in stored})
        except (OSError, json.JSONDecodeError) as e:
            log.warning("thermal guard: ignoring unreadable config: %s", e)
    return _coerce(cfg)


def _coerce(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out["enabled"] = bool(cfg.get("enabled", True))
    for key in ("warn_c", "stop_c", "resume_c"):
        out[key] = float(cfg[key])
    out["poll_seconds"] = int(cfg["poll_seconds"])
    out["warm_extra_delay_ms"] = int(cfg["warm_extra_delay_ms"])
    return out


def validate_config(cfg: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        coerced = _coerce(cfg)
    except (TypeError, ValueError, KeyError) as e:
        return [f"invalid thermal config: {e}"]
    if not (coerced["resume_c"] < coerced["warn_c"] < coerced["stop_c"]):
        errors.append("require resume_c < warn_c < stop_c")
    for key, lo, hi in (
        ("warn_c", 40, 90),
        ("stop_c", 50, 95),
        ("resume_c", 35, 85),
    ):
        if not lo <= coerced[key] <= hi:
            errors.append(f"{key} must be between {lo} and {hi}")
    if not 30 <= coerced["poll_seconds"] <= 60:
        errors.append("poll_seconds must be between 30 and 60")
    if not 0 <= coerced["warm_extra_delay_ms"] <= 120_000:
        errors.append("warm_extra_delay_ms must be between 0 and 120000")
    return errors


def save_config(patch: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    for key in DEFAULTS:
        if key in patch:
            cfg[key] = patch[key]
    cfg = _coerce(cfg)
    errors = validate_config(cfg)
    if errors:
        raise ValueError("; ".join(errors))
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)
    return cfg


def write_guard(tmp_dir: Path, state: str, extra_delay_ms: int, skip_processing: bool) -> None:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_dir / "thermal_guard"
    payload = format_guard_line(state, extra_delay_ms, skip_processing)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(payload)
    os.replace(tmp, target)


def _publish(status: dict[str, Any]) -> None:
    with _LOCK:
        _STATUS.update(status)


def _hold_active() -> bool:
    path = _flag_path()
    if not path.exists():
        return False
    try:
        with path.open() as f:
            return bool(json.load(f).get("capture_stopped_by_us"))
    except (OSError, json.JSONDecodeError):
        return False


def _set_hold(active: bool) -> None:
    path = _flag_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump({"capture_stopped_by_us": active}, f)
    os.replace(tmp, path)


async def _service_active() -> bool:
    from .service import systemctl

    try:
        result = await systemctl("status")
    except Exception as e:  # noqa: BLE001
        log.warning("thermal guard: systemctl status failed: %s", e)
        return False
    return "active (running)" in result.get("stdout", "").lower()


async def _stop_capture() -> None:
    from .service import systemctl

    if not await _service_active():
        return
    log.warning("thermal guard: stopping capture until the CPU cools")
    _set_hold(True)
    try:
        await systemctl("stop")
    except Exception:
        log.exception("thermal guard: failed to stop allsky.service")


async def _resume_capture() -> None:
    from .service import systemctl

    if not _hold_active():
        return
    log.info("thermal guard: CPU cooled, resuming capture")
    try:
        await systemctl("start")
    except Exception:
        log.exception("thermal guard: failed to start allsky.service")
        return
    _set_hold(False)


async def thermal_monitor(stop: asyncio.Event) -> None:
    """Background poller. Safe to run when vcgencmd and the allsky unit are absent."""
    from .paths import paths
    from .system import cpu_temperature, throttle_status

    log.info("thermal guard: starting")
    previous = "ok"
    while not stop.is_set():
        cfg = load_config()
        poll = cfg["poll_seconds"]
        try:
            if not cfg["enabled"]:
                write_guard(paths().tmp, "ok", 0, False)
                if _hold_active():
                    await _resume_capture()
                _publish({
                    **cfg,
                    "state": "ok",
                    "temp_c": cpu_temperature(),
                    "skip_processing": False,
                    "extra_delay_ms": 0,
                    "throttled": False,
                    "capture_held": False,
                    "message": "Thermal guard disabled",
                })
                previous = "ok"
            else:
                temp = cpu_temperature()
                throttle = throttle_status() or {}
                state = decide_state(
                    previous,
                    temp,
                    warn_c=cfg["warn_c"],
                    stop_c=cfg["stop_c"],
                    resume_c=cfg["resume_c"],
                )
                extra, skip = guard_actions(state, cfg["warm_extra_delay_ms"])
                write_guard(paths().tmp, state, extra, skip)
                if state != previous:
                    temp_s = f"{temp:.1f}" if temp is not None else "unknown"
                    log.info("thermal guard: %s -> %s at %s C", previous, state, temp_s)
                if state == "stopped":
                    await _stop_capture()
                elif _hold_active():
                    await _resume_capture()
                if state == "stopped":
                    message = (
                        f"Capture paused at {temp:.1f} C"
                        if temp is not None
                        else "Capture paused"
                    )
                elif state == "warm":
                    message = (
                        f"CPU {temp:.1f} C — longer delay, overlays and watchers paused"
                        if temp is not None
                        else "CPU warm — longer delay, overlays and watchers paused"
                    )
                else:
                    message = "CPU temperature normal"
                _publish({
                    **cfg,
                    "state": state,
                    "temp_c": temp,
                    "skip_processing": skip,
                    "extra_delay_ms": extra,
                    "throttled": bool(throttle.get("throttled_now") or throttle.get("soft_temp_limit_now")),
                    "capture_held": _hold_active(),
                    "message": message,
                })
                previous = state
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("thermal guard: poll failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except asyncio.TimeoutError:
            pass
    log.info("thermal guard: stopped")

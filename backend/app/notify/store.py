"""Persistent config for notification channels + comet watcher.

Two JSON files in DATA_DIR:
  notifiers.json  — list of channels (Telegram, Discord, Email, ntfy, webhook)
  comet_config.json — comet watcher config + comet element list
  focus_config.json — focus alert config + calibration

Credentials are sensitive so files are chmod 0600.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config import get_settings

# ── helpers ──────────────────────────────────────────────────────

def _cfg_path(filename: str) -> Path:
    return get_settings().data_dir / filename


def _load(filename: str, default: Any = None) -> Any:
    p = _cfg_path(filename)
    if not p.exists():
        return default
    with p.open() as f:
        return json.load(f)


def _save(filename: str, data: Any) -> None:
    p = _cfg_path(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2)
    os.replace(str(tmp), str(p))
    try:
        os.chmod(str(p), 0o600)
    except OSError:
        pass


# ── channels ─────────────────────────────────────────────────────

_DEFAULT_CHANNELS: list[dict] = []


def load_channels() -> list[dict]:
    data = _load("notifiers.json", {"channels": _DEFAULT_CHANNELS})
    return data.get("channels", [])


def save_channels(channels: list[dict]) -> None:
    _save("notifiers.json", {"channels": channels})


def redacted_channels() -> list[dict]:
    """Return channels with credentials masked for API responses."""
    out = []
    for ch in load_channels():
        c = {**ch}
        cfg = c.get("config", {})
        redacted = {}
        for k, v in cfg.items():
            if any(s in k.lower() for s in ("token", "pass", "secret", "auth", "key")):
                redacted[k] = "****" if v else ""
            else:
                redacted[k] = v
        c["config"] = redacted
        out.append(c)
    return out


def _find_channel(channel_id: str) -> tuple[list[dict], int | None]:
    channels = load_channels()
    for i, ch in enumerate(channels):
        if ch.get("id") == channel_id:
            return channels, i
    return channels, None


def upsert_channel(channel: dict) -> dict:
    channels, idx = _find_channel(channel["id"])
    if idx is not None:
        channels[idx] = channel
    else:
        channels.append(channel)
    save_channels(channels)
    return channel


def delete_channel(channel_id: str) -> bool:
    channels, idx = _find_channel(channel_id)
    if idx is None:
        return False
    channels.pop(idx)
    save_channels(channels)
    return True


# ── comet config ─────────────────────────────────────────────────

_DEFAULT_COMET_CFG: dict = {
    "enabled": False,
    "poll_interval_minutes": 15,
    "default_mag_threshold": 10.0,
    "default_alt_threshold_deg": 5.0,
    "include_snapshot": True,
    "include_timelapse": True,
    "comets": [],
}


def load_comet_config() -> dict:
    return _load("comet_config.json", {**_DEFAULT_COMET_CFG})


def save_comet_config(cfg: dict) -> None:
    _save("comet_config.json", cfg)


# ── focus config ─────────────────────────────────────────────────

_DEFAULT_FOCUS_CFG: dict = {
    "enabled": False,
    "poll_interval_minutes": 5,
    "baseline_sharpness": None,
    "threshold_pct": 60,
    "consecutive_failures_to_alert": 5,
    "include_snapshot": True,
}


def load_focus_config() -> dict:
    return _load("focus_config.json", {**_DEFAULT_FOCUS_CFG})


def save_focus_config(cfg: dict) -> None:
    _save("focus_config.json", cfg)


# ── rain config ──────────────────────────────────────────────────

_DEFAULT_RAIN_CFG: dict = {
    "enabled": False,
    "poll_interval_minutes": 5,
    "confidence_threshold": 0.4,
    "include_snapshot": True,
}


def load_rain_config() -> dict:
    return _load("rain_config.json", {**_DEFAULT_RAIN_CFG})


def save_rain_config(cfg: dict) -> None:
    _save("rain_config.json", cfg)


# ── ADS-B config ────────────────────────────────────────────────

_DEFAULT_ADSB_CFG: dict = {
    "enabled": False,
    "poll_interval_seconds": 30,
    "radius_km": 50,
    "min_altitude_m": 0,
    "show_on_overlay": True,
    "overlay_max_aircraft": 5,
    "alert_triggers": ["emergency_squawk"],
    "alert_low_altitude_ft": 3000,
    "alert_slow_speed_kts": 100,
    "alert_cooldown_minutes": 30,
    "opensky_username": "",
    "opensky_password": "",
    "include_snapshot": True,
}


def load_adsb_config() -> dict:
    return _load("adsb_config.json", {**_DEFAULT_ADSB_CFG})


def save_adsb_config(cfg: dict) -> None:
    _save("adsb_config.json", cfg)


# ── satellite config ────────────────────────────────────────────

_DEFAULT_SAT_CFG: dict = {
    "enabled": False,
    "poll_interval_minutes": 15,
    "tle_groups": ["stations", "visual"],
    "hours_ahead": 24,
    "min_elevation_deg": 10,
    "alert_triggers": ["iss"],
    "alert_min_elevation_deg": 20,
    "alert_minutes_before": 5,
    "alert_cooldown_minutes": 60,
    "include_snapshot": True,
}


def load_sat_config() -> dict:
    return _load("sat_config.json", {**_DEFAULT_SAT_CFG})


def save_sat_config(cfg: dict) -> None:
    _save("sat_config.json", cfg)

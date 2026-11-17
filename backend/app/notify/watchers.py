"""Background watcher loops that fire alerts through the notification infra.

Watchers run as asyncio tasks during the FastAPI lifespan. Heavy image work
is handed to a worker thread so the event loop keeps serving the API.

Meteor detection follows each new night frame (inotify on tmp/image.jpg).
Focus, rain, ADS-B, and satellite watchers stay off unless their config
enables them. Focus and rain also idle while the thermal guard is warm.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from watchfiles import Change, awatch

from app.allsky.daynight import is_night_now
from app.allsky.paths import paths
from app.allsky.thermal import skip_nonessential
from app.db import connect, insert_alert

from .channels import Attachment, dispatch
from .focus import assess_focus
from .meteor import analyze as analyze_meteor
from .meteor import save_hit
from .adsb import Aircraft, RateLimitError, evaluate_triggers, fetch_metadata, fetch_nearby, is_emergency, min_poll_seconds
from .rain import detect_rain
from .satellites import compute_passes, current_positions, download_tles
from .store import load_adsb_config, load_channels, load_comet_config, load_focus_config, load_rain_config, load_sat_config

log = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────

def _read_file(path: Path, max_mb: float = 10.0) -> bytes | None:
    if not path.exists():
        return None
    try:
        if path.stat().st_size > max_mb * 1024 * 1024:
            return None
        return path.read_bytes()
    except OSError:
        return None


def _build_attachments(
    include_snapshot: bool, include_timelapse: bool,
) -> list[Attachment]:
    atts: list[Attachment] = []
    if include_snapshot:
        data = _read_file(paths().latest_image)
        if data:
            atts.append(Attachment("latest.jpg", data, "image/jpeg"))
    if include_timelapse:
        tl = paths().tmp / "mini-timelapse.mp4"
        data = _read_file(tl)
        if data:
            atts.append(Attachment("timelapse.mp4", data, "video/mp4"))
    return atts


# ── meteor watcher ───────────────────────────────────────────────

def _meteor_state_path() -> Path:
    from app.config import get_settings
    return get_settings().data_dir / "meteor_state.json"


def _load_meteor_state() -> dict:
    path = _meteor_state_path()
    if not path.exists():
        return {}
    try:
        import json
        with path.open() as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_meteor_state(data: dict) -> None:
    import json
    path = _meteor_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def _night_date() -> str:
    """Allsky night folders use the date 12 hours ago so post-midnight stays with that night."""
    return (datetime.now() - timedelta(hours=12)).strftime("%Y%m%d")


async def _commit_meteor(cfg: dict, image, lines, annotated: bytes | None) -> None:
    """Save a confirmed hit and send an alert unless the cooldown is still open."""
    when = datetime.now().astimezone()
    dest = paths().html / "allsky" / "meteors" / _night_date()
    saved = await asyncio.to_thread(save_hit, image, lines, dest, when)
    log.info("meteor_watcher: saved %s (%d streak(s))", saved.get("frame"), len(lines))
    if not _alert_allowed(cfg):
        log.info("meteor_watcher: hit saved, alert suppressed by cooldown")
        return
    _save_meteor_state({"last_alert_ts": time.time()})
    await insert_alert("info", "meteor", f"{len(lines)} meteor(s) detected")
    channels = load_channels()
    atts: list[Attachment] = []
    if annotated:
        atts.append(Attachment("meteor_detected.jpg", annotated, "image/jpeg"))
    subject = f"Meteor detected ({len(lines)})"
    body = (
        f"{len(lines)} meteor streak(s) in a night frame.\n"
        f"Saved under html/allsky/meteors/{_night_date()}/."
    )
    await dispatch(channels, subject, body, atts)
    log.info("meteor_watcher: alerted %d meteor(s)", len(lines))


def _alert_allowed(cfg: dict) -> bool:
    cooldown = float(cfg.get("alert_cooldown_minutes", 10)) * 60.0
    last = float(_load_meteor_state().get("last_alert_ts", 0))
    return (time.time() - last) >= cooldown


async def _handle_meteor_frame(
    target: Path,
    cfg: dict,
    history: list[np.ndarray],
    previous_lines: list[tuple[int, int, int, int]],
    pending: dict | None,
) -> tuple[list[np.ndarray], list[tuple[int, int, int, int]], dict | None]:
    """Run detection in a worker thread. Returns updated history, lines, and pending hit."""
    from .meteor import line_continues

    mask_path = paths().masks_dir / "mask.png"
    min_length = int(cfg.get("min_streak_length", 100))
    result, small, original = await asyncio.to_thread(
        analyze_meteor,
        target,
        min_length,
        0,
        True,
        mask_path if mask_path.exists() else None,
        history[-1] if history else None,
        list(history),
        previous_lines,
    )
    if small is None or original is None:
        return history, previous_lines, pending

    # Confirm the previous frame's streak only if it did not continue into this one.
    if pending and pending.get("lines"):
        h, w = pending["image"].shape[:2]
        survivors = [
            ln for ln in pending["lines"]
            if not line_continues(ln, result.candidate_lines, w, h)
        ]
        if survivors:
            await _commit_meteor(cfg, pending["image"], survivors, pending.get("annotated"))

    history = (history + [small])[-3:]
    new_pending = None
    if result.candidate_lines:
        new_pending = {
            "lines": list(result.candidate_lines),
            "image": original,
            "annotated": result.annotated_jpeg,
        }
    return history, list(result.candidate_lines), new_pending


async def meteor_watcher(stop: asyncio.Event) -> None:
    """Detect meteors on every new night frame. Never sleeps for minutes between frames."""
    log.info("meteor_watcher: starting")
    warned_location = False
    history: list[np.ndarray] = []
    previous_lines: list[tuple[int, int, int, int]] = []
    pending: dict | None = None

    while not stop.is_set():
        try:
            cfg = load_comet_config()
            if not cfg.get("enabled"):
                if pending and pending.get("lines"):
                    await _commit_meteor(cfg, pending["image"], pending["lines"], pending.get("annotated"))
                history.clear()
                previous_lines = []
                pending = None
                await _sleep(stop, 30)
                continue

            target = paths().latest_image
            target.parent.mkdir(parents=True, exist_ok=True)
            last_mtime = target.stat().st_mtime if target.exists() else 0.0

            async for changes in awatch(target.parent, stop_event=stop, debounce=300, step=100):
                if stop.is_set():
                    return
                cfg = load_comet_config()
                if not cfg.get("enabled"):
                    break
                relevant = any(
                    p == str(target) and ctype in (Change.added, Change.modified)
                    for ctype, p in changes
                )
                if not relevant or not target.exists():
                    continue
                try:
                    mtime = target.stat().st_mtime
                except OSError:
                    continue
                if mtime <= last_mtime:
                    continue
                last_mtime = mtime

                night = is_night_now()
                if night is None and not warned_location:
                    log.warning("meteor_watcher: latitude/longitude unset; night-only detection is idle")
                    warned_location = True
                if night is not True:
                    if pending and pending.get("lines"):
                        await _commit_meteor(cfg, pending["image"], pending["lines"], pending.get("annotated"))
                    history.clear()
                    previous_lines = []
                    pending = None
                    continue

                history, previous_lines, pending = await _handle_meteor_frame(
                    target, cfg, history, previous_lines, pending,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("meteor_watcher: error")
            await _sleep(stop, 5)

    log.info("meteor_watcher: stopped")


# ── focus watcher ────────────────────────────────────────────────

async def focus_watcher(stop: asyncio.Event) -> None:
    log.info("focus_watcher: starting")
    consecutive_soft = 0

    while not stop.is_set():
        try:
            cfg = load_focus_config()
            if not cfg.get("enabled"):
                consecutive_soft = 0
                await _sleep(stop, 30)
                continue
            if skip_nonessential():
                await _sleep(stop, 30)
                continue

            target = paths().latest_image
            if not target.exists():
                await _sleep(stop, 10)
                continue

            baseline = cfg.get("baseline_sharpness")
            threshold_pct = cfg.get("threshold_pct", 60)
            needed = cfg.get("consecutive_failures_to_alert", 5)

            mask_path = paths().masks_dir / "mask.png"
            result = assess_focus(
                target, baseline, threshold_pct,
                mask_path=mask_path if mask_path.exists() else None,
            )
            if result["status"] == "soft":
                consecutive_soft += 1
                log.debug("focus_watcher: soft (%d/%d)", consecutive_soft, needed)
                if consecutive_soft >= needed:
                    today = date.today().isoformat()
                    if not await _already_alerted("focus", today):
                        await _record_alert("focus", today)
                        await insert_alert(
                            "warning", "focus",
                            f"Camera may be out of focus (score {result['score']}, "
                            f"baseline {result['baseline']}, threshold {result['threshold']})"
                        )
                        channels = load_channels()
                        atts = _build_attachments(cfg.get("include_snapshot", True), False)
                        subject = "Allsky: camera may be out of focus"
                        body = (
                            f"Sharpness score {result['score']} is below the threshold "
                            f"{result['threshold']} (baseline {result['baseline']}) for "
                            f"{consecutive_soft} consecutive checks."
                        )
                        await dispatch(channels, subject, body, atts)
                        log.info("focus_watcher: alerted (score=%s)", result["score"])
            else:
                if consecutive_soft > 0:
                    log.debug("focus_watcher: back to normal")
                consecutive_soft = 0

            poll = cfg.get("poll_interval_minutes", 5)
            await _sleep(stop, poll * 60)

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("focus_watcher: error")
            await _sleep(stop, 60)

    log.info("focus_watcher: stopped")


# ── rain watcher ────────────────────────────────────────────────

async def rain_watcher(stop: asyncio.Event) -> None:
    """Periodically check for rain/moisture on the dome."""
    log.info("rain_watcher: starting")

    while not stop.is_set():
        try:
            cfg = load_rain_config()
            if not cfg.get("enabled"):
                await _sleep(stop, 30)
                continue
            if skip_nonessential():
                await _sleep(stop, 30)
                continue

            target = paths().latest_image
            try:
                if not target.exists():
                    await _sleep(stop, 10)
                    continue
            except OSError:
                await _sleep(stop, 10)
                continue

            mask_path = paths().masks_dir / "mask.png"
            result = detect_rain(
                target,
                mask_path=mask_path if mask_path.exists() else None,
                confidence_threshold=cfg.get("confidence_threshold", 0.4),
            )

            if result.rain_detected:
                today = date.today().isoformat()
                if await _already_alerted("rain", today):
                    poll = cfg.get("poll_interval_minutes", 5)
                    await _sleep(stop, poll * 60)
                    continue

                await _record_alert("rain", today)
                await insert_alert("warning", "rain",
                    f"Rain/moisture detected on dome (confidence: {result.confidence:.0%})")

                channels = load_channels()
                atts = _build_attachments(cfg.get("include_snapshot", True), False)

                subject = "Rain detected on dome"
                body = (
                    f"Moisture/rain detected on the allsky dome.\n"
                    f"Confidence: {result.confidence:.0%}\n"
                    f"Details: {result.message}"
                )
                await dispatch(channels, subject, body, atts)
                log.info("rain_watcher: alerted (confidence=%.2f)", result.confidence)

            poll = cfg.get("poll_interval_minutes", 5)
            await _sleep(stop, poll * 60)

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("rain_watcher: error")
            await _sleep(stop, 60)

    log.info("rain_watcher: stopped")


# ── ADS-B watcher ──────────────────────────────────────────────

_adsb_cache: dict = {"aircraft": [], "timestamp": 0, "count": 0}
_adsb_alert_times: dict[str, float] = {}


def get_adsb_cache() -> dict:
    return dict(_adsb_cache)


def set_adsb_cache(data: dict) -> None:
    _adsb_cache.update(data)


def _parse_coord(s: str, neg_letter: str) -> float | None:
    s = str(s).strip()
    if not s:
        return None
    sign = -1 if s.upper().endswith(neg_letter) else 1
    s = s.rstrip("NSEWnsew").strip()
    try:
        return float(s) * sign
    except ValueError:
        return None


def _get_camera_latlon() -> tuple[float, float] | None:
    """Read camera lat/lon from allsky settings."""
    try:
        import json
        settings_path = paths().home / "config" / "settings.json"
        if not settings_path.exists():
            return None
        with settings_path.open() as f:
            settings = json.load(f)
        lat = _parse_coord(settings.get("latitude", ""), "S")
        lon = _parse_coord(settings.get("longitude", ""), "W")
        if lat is None or lon is None:
            return None
        return (lat, lon)
    except Exception:
        return None


async def adsb_watcher(stop: asyncio.Event) -> None:
    """Poll OpenSky Network for nearby aircraft and cache results."""
    log.info("adsb_watcher: starting")

    while not stop.is_set():
        try:
            cfg = load_adsb_config()
            if not cfg.get("enabled"):
                _adsb_cache.update({"aircraft": [], "timestamp": 0, "count": 0})
                await _sleep(stop, 30)
                continue

            latlon = _get_camera_latlon()
            if latlon is None:
                log.debug("adsb_watcher: no lat/lon configured")
                await _sleep(stop, 60)
                continue

            lat, lon = latlon
            uname = cfg.get("opensky_username", "")
            passwd = cfg.get("opensky_password", "")
            min_interval = min_poll_seconds(uname, passwd)

            try:
                aircraft = await fetch_nearby(
                    lat, lon,
                    radius_km=cfg.get("radius_km", 50),
                    min_altitude_m=cfg.get("min_altitude_m", 0),
                    username=uname,
                    password=passwd,
                )
            except RateLimitError:
                log.warning("adsb_watcher: rate limited, backing off 120s")
                await _sleep(stop, 120)
                continue
            except Exception as e:
                log.warning("adsb_watcher: OpenSky API error: %s", e)
                await _sleep(stop, max(cfg.get("poll_interval_seconds", 30), min_interval))
                continue

            # Enrich one aircraft per cycle with metadata (rate-limit friendly).
            if aircraft:
                _adsb_meta_idx = getattr(adsb_watcher, '_meta_idx', 0)
                target = aircraft[_adsb_meta_idx % len(aircraft)]
                meta = await fetch_metadata(target.icao24, uname, passwd)
                if meta:
                    target.registration = meta.get("registration", "")
                    target.aircraft_type = meta.get("aircraft_type", "")
                    if not target.aircraft_type and meta.get("model"):
                        target.aircraft_type = meta["model"]
                    target.operator = meta.get("operator", "")
                adsb_watcher._meta_idx = _adsb_meta_idx + 1

            _adsb_cache["aircraft"] = [ac.to_dict() for ac in aircraft]
            _adsb_cache["timestamp"] = time.time()
            _adsb_cache["count"] = len(aircraft)

            triggers = cfg.get("alert_triggers", [])
            cooldown = cfg.get("alert_cooldown_minutes", 30) * 60
            now = time.time()
            if triggers:
                for ac in aircraft:
                    matched = evaluate_triggers(ac, triggers, cfg)
                    for trig in matched:
                        last = _adsb_alert_times.get(trig.dedup_key, 0)
                        if now - last < cooldown:
                            continue
                        today = date.today().isoformat()
                        if await _already_alerted(trig.dedup_key, today):
                            continue
                        await _record_alert(trig.dedup_key, today)
                        _adsb_alert_times[trig.dedup_key] = now
                        level = "warning" if trig.kind == "emergency_squawk" else "info"
                        await insert_alert(level, "adsb", trig.message)
                        channels = load_channels()
                        atts = _build_attachments(cfg.get("include_snapshot", True), False)
                        subject = f"ADS-B [{trig.kind}]: {ac.callsign or ac.icao24}"
                        await dispatch(channels, subject, trig.message, atts)
                        log.info("adsb_watcher: %s — %s", trig.kind, trig.message)

            poll = cfg.get("poll_interval_seconds", 30)
            await _sleep(stop, max(poll, min_interval))

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("adsb_watcher: error")
            await _sleep(stop, 60)

    log.info("adsb_watcher: stopped")


# ── satellite watcher ──────────────────────────────────────────

_sat_cache: dict = {"passes": [], "overhead": [], "timestamp": 0}
_sat_alert_times: dict[str, float] = {}

_SAT_TRIGGER_LABELS = {
    "iss": "ISS",
    "all_visible": "any visible satellite",
    "bright_passes": "bright passes (>45° elevation)",
    "starlink": "Starlink satellite",
    "space_station": "any space station",
}


def get_sat_cache() -> dict:
    return dict(_sat_cache)


def set_sat_cache(data: dict) -> None:
    _sat_cache.update(data)


async def satellite_watcher(stop: asyncio.Event) -> None:
    """Compute upcoming satellite passes and alert before interesting ones."""
    log.info("satellite_watcher: starting")

    while not stop.is_set():
        try:
            cfg = load_sat_config()
            if not cfg.get("enabled"):
                _sat_cache.update({"passes": [], "overhead": [], "timestamp": 0})
                await _sleep(stop, 30)
                continue

            latlon = _get_camera_latlon()
            if latlon is None:
                await _sleep(stop, 60)
                continue
            lat, lon = latlon

            groups = cfg.get("tle_groups", ["stations", "visual"])
            try:
                tles = await download_tles(groups)
            except Exception as e:
                log.warning("satellite_watcher: TLE download failed: %s", e)
                await _sleep(stop, cfg.get("poll_interval_minutes", 15) * 60)
                continue

            hours = cfg.get("hours_ahead", 24)
            min_elev = cfg.get("min_elevation_deg", 10)
            passes = compute_passes(lat, lon, 0, tles, hours, min_elev)
            overhead = current_positions(lat, lon, 0, tles, min_elevation_deg=0)

            _sat_cache["passes"] = [p.to_dict() for p in passes[:50]]
            _sat_cache["overhead"] = [s.to_dict() for s in overhead]
            _sat_cache["timestamp"] = time.time()

            # Check alert triggers.
            triggers = cfg.get("alert_triggers", [])
            cooldown = cfg.get("alert_cooldown_minutes", 60) * 60
            alert_min_elev = cfg.get("alert_min_elevation_deg", 20)
            alert_before = cfg.get("alert_minutes_before", 5)
            now = time.time()

            for p in passes:
                if not p.is_visible:
                    continue
                if p.max_elev_deg < alert_min_elev:
                    continue
                try:
                    from datetime import datetime
                    rise_dt = datetime.fromisoformat(p.rise_time)
                    minutes_until = (rise_dt.timestamp() - now) / 60
                    if minutes_until < 0 or minutes_until > alert_before:
                        continue
                except Exception:
                    continue

                should_alert = False
                name_lower = p.name.lower()

                if "iss" in triggers and "iss" in name_lower:
                    should_alert = True
                if "space_station" in triggers and ("iss" in name_lower or "tiangong" in name_lower or "css" in name_lower):
                    should_alert = True
                if "starlink" in triggers and "starlink" in name_lower:
                    should_alert = True
                if "bright_passes" in triggers and p.max_elev_deg >= 45:
                    should_alert = True
                if "all_visible" in triggers:
                    should_alert = True

                if not should_alert:
                    continue

                dedup_key = f"sat-{p.norad_id}-{p.rise_time[:13]}"
                last = _sat_alert_times.get(dedup_key, 0)
                if now - last < cooldown:
                    continue
                today = date.today().isoformat()
                if await _already_alerted(dedup_key, today):
                    continue
                await _record_alert(dedup_key, today)
                _sat_alert_times[dedup_key] = now

                msg = (
                    f"{p.name} pass in {int(minutes_until)} min — "
                    f"max {p.max_elev_deg}° elev, "
                    f"{p.duration_sec}s duration, "
                    f"rise {p.rise_time[11:16]} UTC"
                )
                await insert_alert("info", "satellite", msg)
                channels = load_channels()
                atts = _build_attachments(cfg.get("include_snapshot", True), False)
                await dispatch(channels, f"Satellite: {p.name} pass soon", msg, atts)
                log.info("satellite_watcher: alert — %s", msg)

            poll = cfg.get("poll_interval_minutes", 15)
            await _sleep(stop, poll * 60)

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("satellite_watcher: error")
            await _sleep(stop, 120)

    log.info("satellite_watcher: stopped")


# ── dedup helpers ────────────────────────────────────────────────

async def _already_alerted(kind: str, day: str) -> bool:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM alert_dedup WHERE kind=? AND day=?", (kind, day)
        )
        return (await cur.fetchone()) is not None


async def _record_alert(kind: str, day: str) -> None:
    async with connect() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO alert_dedup(kind, day) VALUES(?, ?)", (kind, day)
        )
        await conn.commit()


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    """Sleep that wakes early if stop is set."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass

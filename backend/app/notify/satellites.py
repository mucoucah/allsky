"""Satellite pass prediction using TLE data from CelesTrak.

Downloads TLE (Two-Line Element) data for bright satellites (ISS, Starlink,
Hubble, etc.) and computes visible passes from the camera's location using
the ephem library.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

import ephem
import httpx

log = logging.getLogger(__name__)

_TLE_URLS = {
    "stations": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "visual": "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle",
    "starlink": "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
}

_TLE_CACHE: dict[str, tuple[float, list[tuple[str, str, str]]]] = {}
_TLE_TTL = 43200  # 12 hours


@dataclass
class SatellitePass:
    name: str
    norad_id: str
    rise_time: str
    rise_az_deg: float
    culmination_time: str
    max_elev_deg: float
    set_time: str
    set_az_deg: float
    duration_sec: int
    is_visible: bool
    group: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SatelliteInfo:
    name: str
    norad_id: str
    lat: float
    lon: float
    altitude_km: float
    velocity_kms: float
    elevation_deg: float
    azimuth_deg: float
    range_km: float
    is_sunlit: bool
    group: str

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_tles(text: str) -> list[tuple[str, str, str]]:
    """Parse TLE text into list of (name, line1, line2) tuples."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    tles = []
    i = 0
    while i + 2 < len(lines):
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            tles.append((lines[i], lines[i + 1], lines[i + 2]))
            i += 3
        else:
            i += 1
    return tles


async def download_tles(groups: list[str] | None = None) -> dict[str, list[tuple[str, str, str]]]:
    """Download TLE data from CelesTrak. Returns {group: [(name, l1, l2), ...]}."""
    if groups is None:
        groups = ["stations", "visual"]
    now = time.time()
    result: dict[str, list[tuple[str, str, str]]] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        for group in groups:
            url = _TLE_URLS.get(group)
            if not url:
                continue
            cached = _TLE_CACHE.get(group)
            if cached and now - cached[0] < _TLE_TTL:
                result[group] = cached[1]
                continue
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                tles = _parse_tles(resp.text)
                _TLE_CACHE[group] = (now, tles)
                result[group] = tles
                log.info("Downloaded %d TLEs for group '%s'", len(tles), group)
            except Exception as e:
                log.warning("Failed to download TLEs for '%s': %s", group, e)
                if cached:
                    result[group] = cached[1]

    return result


def _extract_norad_id(line1: str) -> str:
    """Extract NORAD catalog number from TLE line 1."""
    try:
        return line1[2:7].strip()
    except (IndexError, ValueError):
        return ""


def compute_passes(
    lat: float,
    lon: float,
    elevation_m: float,
    tles: dict[str, list[tuple[str, str, str]]],
    hours_ahead: float = 24.0,
    min_elevation_deg: float = 10.0,
) -> list[SatellitePass]:
    """Compute upcoming visible satellite passes."""
    observer = ephem.Observer()
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.elevation = elevation_m
    observer.pressure = 0

    now = ephem.now()
    end = ephem.Date(now + hours_ahead / 24.0)
    passes: list[SatellitePass] = []

    for group, tle_list in tles.items():
        for name, line1, line2 in tle_list:
            try:
                sat = ephem.readtle(name, line1, line2)
            except Exception:
                continue

            observer.date = now
            try:
                while observer.date < end:
                    try:
                        info = observer.next_pass(sat)
                    except Exception:
                        break
                    if info[0] is None:
                        break

                    rise_time, rise_az, culm_time, max_elev, set_time, set_az = info

                    if max_elev is not None and math.degrees(max_elev) >= min_elevation_deg:
                        duration = 0
                        if rise_time and set_time:
                            duration = int((set_time - rise_time) * 86400)

                        # Check if satellite is sunlit at culmination (visible).
                        is_visible = False
                        if culm_time:
                            observer.date = culm_time
                            try:
                                sat.compute(observer)
                                is_visible = not sat.eclipsed
                            except Exception:
                                pass

                        passes.append(SatellitePass(
                            name=name.strip(),
                            norad_id=_extract_norad_id(line1),
                            rise_time=_ephem_to_iso(rise_time) if rise_time else "",
                            rise_az_deg=round(math.degrees(rise_az), 1) if rise_az else 0,
                            culmination_time=_ephem_to_iso(culm_time) if culm_time else "",
                            max_elev_deg=round(math.degrees(max_elev), 1) if max_elev else 0,
                            set_time=_ephem_to_iso(set_time) if set_time else "",
                            set_az_deg=round(math.degrees(set_az), 1) if set_az else 0,
                            duration_sec=duration,
                            is_visible=is_visible,
                            group=group,
                        ))

                    observer.date = (set_time or rise_time) + ephem.minute if (set_time or rise_time) else end
            except StopIteration:
                pass

    passes.sort(key=lambda p: p.rise_time)
    return passes


def current_positions(
    lat: float,
    lon: float,
    elevation_m: float,
    tles: dict[str, list[tuple[str, str, str]]],
    min_elevation_deg: float = 0.0,
    names_filter: list[str] | None = None,
) -> list[SatelliteInfo]:
    """Get current positions of satellites above the horizon."""
    observer = ephem.Observer()
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.elevation = elevation_m
    observer.pressure = 0
    observer.date = ephem.now()

    visible: list[SatelliteInfo] = []

    for group, tle_list in tles.items():
        for name, line1, line2 in tle_list:
            if names_filter and not any(n.lower() in name.lower() for n in names_filter):
                continue
            try:
                sat = ephem.readtle(name, line1, line2)
                sat.compute(observer)
            except Exception:
                continue

            elev = math.degrees(sat.alt)
            if elev < min_elevation_deg:
                continue

            sublat = math.degrees(sat.sublat)
            sublon = math.degrees(sat.sublong)
            alt_km = sat.elevation / 1000.0
            range_km = sat.range / 1000.0
            vel = math.sqrt(398600.4418 / (6371 + alt_km)) if alt_km > 0 else 0

            visible.append(SatelliteInfo(
                name=name.strip(),
                norad_id=_extract_norad_id(line1),
                lat=round(sublat, 4),
                lon=round(sublon, 4),
                altitude_km=round(alt_km, 1),
                velocity_kms=round(vel, 1),
                elevation_deg=round(elev, 1),
                azimuth_deg=round(math.degrees(sat.az), 1),
                range_km=round(range_km, 1),
                is_sunlit=not sat.eclipsed,
                group=group,
            ))

    visible.sort(key=lambda s: s.elevation_deg, reverse=True)
    return visible


def _ephem_to_iso(d: ephem.Date) -> str:
    dt = ephem.Date(d).datetime().replace(tzinfo=timezone.utc)
    return dt.isoformat()

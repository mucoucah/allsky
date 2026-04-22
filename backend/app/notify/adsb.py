"""ADS-B aircraft tracking via the OpenSky Network REST API.

Fetches nearby aircraft positions relative to the allsky camera's lat/lon,
computes distance/bearing/elevation, and flags emergency squawk codes.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, asdict

import httpx

log = logging.getLogger(__name__)

_OPENSKY_URL = "https://opensky-network.org/api/states/all"
_EARTH_R_KM = 6371.0
_TIMEOUT = 15.0


@dataclass
class Aircraft:
    icao24: str
    callsign: str
    origin_country: str
    lat: float
    lon: float
    altitude_m: float | None
    velocity_mps: float | None
    heading_deg: float | None
    vertical_rate: float | None
    on_ground: bool
    squawk: str | None
    distance_km: float
    bearing_deg: float
    elevation_deg: float

    def to_dict(self) -> dict:
        return asdict(self)


_EMERGENCY_SQUAWKS = {
    "7500": "hijack",
    "7600": "radio failure",
    "7700": "emergency",
}


def is_emergency(ac: Aircraft) -> str | None:
    if ac.squawk and ac.squawk.strip() in _EMERGENCY_SQUAWKS:
        return _EMERGENCY_SQUAWKS[ac.squawk.strip()]
    return None


@dataclass
class AlertTrigger:
    kind: str  # "emergency_squawk", "all_flights", "low_altitude", "slow_mover", "no_callsign"
    dedup_key: str
    message: str


def evaluate_triggers(ac: Aircraft, triggers: list[str], cfg: dict) -> list[AlertTrigger]:
    """Check which alert triggers an aircraft matches. Returns list of matched triggers."""
    matched: list[AlertTrigger] = []

    if "emergency_squawk" in triggers:
        em = is_emergency(ac)
        if em:
            matched.append(AlertTrigger(
                kind="emergency_squawk",
                dedup_key=f"adsb-emerg-{ac.icao24}",
                message=(
                    f"Emergency squawk {ac.squawk} ({em}) — "
                    f"{ac.callsign or ac.icao24} at {_fmt_alt(ac.altitude_m)}, "
                    f"{ac.distance_km} km away, bearing {ac.bearing_deg}°"
                ),
            ))

    if "all_flights" in triggers:
        matched.append(AlertTrigger(
            kind="all_flights",
            dedup_key=f"adsb-all-{ac.icao24}",
            message=(
                f"Aircraft overhead: {ac.callsign or ac.icao24} "
                f"({ac.origin_country}) at {_fmt_alt(ac.altitude_m)}, "
                f"{ac.distance_km} km away"
            ),
        ))

    if "low_altitude" in triggers:
        threshold_ft = cfg.get("alert_low_altitude_ft", 3000)
        if ac.altitude_m is not None and ac.altitude_m * 3.281 < threshold_ft:
            matched.append(AlertTrigger(
                kind="low_altitude",
                dedup_key=f"adsb-low-{ac.icao24}",
                message=(
                    f"Low-altitude flight: {ac.callsign or ac.icao24} at "
                    f"{_fmt_alt(ac.altitude_m)} (threshold: {threshold_ft} ft), "
                    f"{ac.distance_km} km away"
                ),
            ))

    if "slow_mover" in triggers:
        threshold_kts = cfg.get("alert_slow_speed_kts", 100)
        if ac.velocity_mps is not None and ac.velocity_mps * 1.944 < threshold_kts:
            speed_kts = round(ac.velocity_mps * 1.944)
            matched.append(AlertTrigger(
                kind="slow_mover",
                dedup_key=f"adsb-slow-{ac.icao24}",
                message=(
                    f"Slow/hovering aircraft: {ac.callsign or ac.icao24} at "
                    f"{speed_kts} kts (threshold: {threshold_kts} kts), "
                    f"{_fmt_alt(ac.altitude_m)}, {ac.distance_km} km away"
                ),
            ))

    if "no_callsign" in triggers:
        if not ac.callsign or not ac.callsign.strip():
            matched.append(AlertTrigger(
                kind="no_callsign",
                dedup_key=f"adsb-nocall-{ac.icao24}",
                message=(
                    f"No-callsign aircraft: {ac.icao24} ({ac.origin_country}) at "
                    f"{_fmt_alt(ac.altitude_m)}, {ac.distance_km} km away"
                ),
            ))

    return matched


def _fmt_alt(m: float | None) -> str:
    if m is None:
        return "unknown alt"
    return f"{round(m * 3.281):,} ft"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return _EARTH_R_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees (0=N, 90=E)."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlon = rlon2 - rlon1
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _elevation_angle(distance_km: float, altitude_m: float | None) -> float:
    """Approximate elevation angle from ground to aircraft."""
    if altitude_m is None or altitude_m <= 0 or distance_km <= 0:
        return 0.0
    altitude_km = altitude_m / 1000.0
    return math.degrees(math.atan2(altitude_km, distance_km))


def _bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Bounding box (lamin, lomin, lamax, lomax) around a point."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


async def fetch_nearby(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
    min_altitude_m: float = 0.0,
    username: str = "",
    password: str = "",
) -> list[Aircraft]:
    """Query OpenSky for aircraft within radius_km of (lat, lon)."""
    lamin, lomin, lamax, lomax = _bbox(lat, lon, radius_km)
    params = {
        "lamin": f"{lamin:.4f}",
        "lomin": f"{lomin:.4f}",
        "lamax": f"{lamax:.4f}",
        "lomax": f"{lomax:.4f}",
    }

    auth = None
    if username and password:
        auth = (username, password)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_OPENSKY_URL, params=params, auth=auth)
        resp.raise_for_status()
        data = resp.json()

    states = data.get("states") or []
    aircraft: list[Aircraft] = []

    for s in states:
        if len(s) < 17:
            continue
        on_ground = bool(s[8])
        if on_ground:
            continue
        ac_lat = s[6]
        ac_lon = s[5]
        if ac_lat is None or ac_lon is None:
            continue
        altitude = s[7]  # baro_altitude in meters
        if min_altitude_m > 0 and (altitude is None or altitude < min_altitude_m):
            continue

        dist = _haversine(lat, lon, ac_lat, ac_lon)
        if dist > radius_km:
            continue

        ac = Aircraft(
            icao24=str(s[0] or "").strip(),
            callsign=str(s[1] or "").strip(),
            origin_country=str(s[2] or ""),
            lat=ac_lat,
            lon=ac_lon,
            altitude_m=altitude,
            velocity_mps=s[9],
            heading_deg=s[10],
            vertical_rate=s[11],
            on_ground=on_ground,
            squawk=str(s[14]) if s[14] else None,
            distance_km=round(dist, 1),
            bearing_deg=round(_bearing(lat, lon, ac_lat, ac_lon), 1),
            elevation_deg=round(_elevation_angle(dist, altitude), 1),
        )
        aircraft.append(ac)

    aircraft.sort(key=lambda a: a.distance_km)
    return aircraft

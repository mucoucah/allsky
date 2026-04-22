"""ADS-B aircraft tracking via the OpenSky Network REST API.

Fetches nearby aircraft positions relative to the allsky camera's lat/lon,
computes distance/bearing/elevation, and flags emergency squawk codes.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, asdict

import httpx

log = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


_OPENSKY_URL = "https://opensky-network.org/api/states/all"
_EARTH_R_KM = 6371.0
_TIMEOUT = 15.0
_MAX_BBOX_DEG = 25.0  # OpenSky enforces max 25° × 25° bounding box

# Rate limits per tier (seconds between requests).
RATE_LIMIT_ANONYMOUS = 6    # ~10 req/min
RATE_LIMIT_REGISTERED = 3   # ~4 req/10s = 2.5s, use 3s for safety


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
    # Enriched fields from state vector
    geo_altitude_m: float | None = None
    position_source: str = ""
    category: str = ""
    spi: bool = False
    last_contact_age: int = 0
    # Enriched from metadata API (filled async by watcher)
    registration: str = ""
    aircraft_type: str = ""
    operator: str = ""

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


_CATEGORY_MAP = {
    0: "", 1: "No info", 2: "Light (<15.5k lbs)", 3: "Medium (15.5k-75k lbs)",
    4: "Heavy (>75k lbs)", 5: "High vortex", 6: "Very heavy (>300k lbs)",
    7: "Rotorcraft", 8: "Glider/sailplane", 9: "Lighter-than-air",
    10: "Skydiver", 11: "Paraglider/hang-glider", 12: "Reserved",
    13: "UAV/drone", 14: "Space vehicle", 15: "Emergency vehicle",
    16: "Service vehicle", 17: "Obstruction",
}

_POSITION_SOURCE_MAP = {0: "ADS-B", 1: "MLAT", 2: "Other", 3: "FLARM"}

_metadata_cache: dict[str, tuple[float, dict]] = {}  # icao24 -> (timestamp, data)
_METADATA_TTL = 86400  # 24 hours


async def fetch_metadata(
    icao24: str, username: str = "", password: str = "",
) -> dict | None:
    """Fetch aircraft metadata (type, registration, operator) from OpenSky."""
    now = time.time()
    cached = _metadata_cache.get(icao24)
    if cached and now - cached[0] < _METADATA_TTL:
        return cached[1]

    url = f"https://opensky-network.org/api/metadata/aircraft/icao/{icao24}"
    auth = (username, password) if username and password else None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, auth=auth)
            if resp.status_code == 404:
                _metadata_cache[icao24] = (now, {})
                return {}
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            data = resp.json()
            result = {
                "registration": (data.get("registration") or "").strip(),
                "aircraft_type": (data.get("typecode") or "").strip(),
                "operator": (data.get("operatorCallsign") or data.get("owner") or "").strip(),
                "model": (data.get("model") or "").strip(),
                "manufacturer": (data.get("manufacturerName") or "").strip(),
            }
            _metadata_cache[icao24] = (now, result)
            return result
    except Exception as e:
        log.debug("metadata fetch failed for %s: %s", icao24, e)
        return None


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


def min_poll_seconds(username: str = "", password: str = "") -> int:
    """Minimum seconds between API calls based on auth tier."""
    if username and password:
        return RATE_LIMIT_REGISTERED
    return RATE_LIMIT_ANONYMOUS


def _bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Bounding box (lamin, lomin, lamax, lomax) around a point.

    Clamped to OpenSky's 25° × 25° maximum.
    """
    dlat = min(radius_km / 111.0, _MAX_BBOX_DEG / 2)
    dlon = min(radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01)), _MAX_BBOX_DEG / 2)
    return (
        max(lat - dlat, -90),
        max(lon - dlon, -180),
        min(lat + dlat, 90),
        min(lon + dlon, 180),
    )


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
        if resp.status_code == 429:
            log.warning("OpenSky rate limit hit (429). Back off and retry later.")
            raise RateLimitError("OpenSky rate limit exceeded")
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

        now_ts = data.get("time", time.time())
        last_contact = s[4] if len(s) > 4 and s[4] else now_ts
        cat_code = s[17] if len(s) > 17 and s[17] is not None else 0
        pos_src = s[16] if len(s) > 16 and s[16] is not None else 0

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
            geo_altitude_m=s[13] if len(s) > 13 else None,
            position_source=_POSITION_SOURCE_MAP.get(pos_src, ""),
            category=_CATEGORY_MAP.get(cat_code, ""),
            spi=bool(s[15]) if len(s) > 15 else False,
            last_contact_age=max(0, int(now_ts - last_contact)),
        )
        aircraft.append(ac)

    aircraft.sort(key=lambda a: a.distance_km)
    return aircraft

"""Sun-based day/night, shared by the meteor watcher.

Returns None when latitude/longitude are not set, so callers can avoid
guessing. Night is sun elevation at or below the Allsky `angle` setting
(default civil twilight, -6 degrees).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


def _parse_coord(value: object, neg_letter: str) -> float | None:
    s = str(value or "").strip()
    if not s:
        return None
    sign = -1 if s.upper().endswith(neg_letter) else 1
    s = s.rstrip("NSEWnsew").strip()
    try:
        return float(s) * sign
    except ValueError:
        return None


def is_night_now() -> bool | None:
    """True at night, False during the day, None if location is unset."""
    try:
        import ephem
    except ImportError:
        return None
    from .settings import load_values

    settings = load_values()
    lat = _parse_coord(settings.get("latitude", ""), "S")
    lon = _parse_coord(settings.get("longitude", ""), "W")
    if lat is None or lon is None:
        return None
    try:
        angle = float(settings.get("angle", -6))
    except (TypeError, ValueError):
        angle = -6.0
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.date = datetime.now(timezone.utc)
    sun = ephem.Sun()
    sun.compute(obs)
    elevation = float(sun.alt) * 180.0 / math.pi
    return elevation <= angle

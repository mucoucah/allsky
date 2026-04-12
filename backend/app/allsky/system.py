"""Host (Raspberry Pi) telemetry — CPU temp, disk, uptime, load."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

from .paths import paths


def _read_thermal_zone() -> float | None:
    """Linux generic thermal zone (works on Pi 3B/4/5 without vcgencmd)."""
    p = Path("/sys/class/thermal/thermal_zone0/temp")
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _vcgencmd_temp() -> float | None:
    try:
        out = subprocess.run(
            ["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=2
        )
        if out.returncode != 0:
            return None
        # "temp=51.0'C\n"
        return float(out.stdout.split("=")[1].split("'")[0])
    except (FileNotFoundError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def cpu_temperature() -> float | None:
    return _read_thermal_zone() or _vcgencmd_temp()


def system_snapshot() -> dict[str, Any]:
    """One-shot reading of system telemetry for the dashboard."""
    images_dir = paths().images
    disk_target = images_dir if images_dir.exists() else Path("/")
    du = psutil.disk_usage(str(disk_target))

    load1, load5, load15 = psutil.getloadavg()

    return {
        "boot_time": int(psutil.boot_time()),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_temp_c": cpu_temperature(),
        "load_avg": {"1m": load1, "5m": load5, "15m": load15},
        "memory": {
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent,
        },
        "disk": {
            "path": str(disk_target),
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": du.percent,
        },
    }

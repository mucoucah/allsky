"""Host (Raspberry Pi) telemetry — CPU temp, disk, uptime, load, network, throttle."""
from __future__ import annotations

import platform
import re
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


def _dir_size(p: Path) -> int:
    """Total bytes used by a directory tree (non-recursive stat)."""
    try:
        if not p.exists():
            return 0
    except OSError:
        return 0
    try:
        total = 0
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _network_info() -> list[dict[str, Any]]:
    """Return a list of network interfaces with their addresses."""
    out: list[dict[str, Any]] = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=True)
    for iface, addr_list in sorted(addrs.items()):
        if iface == "lo":
            continue
        info: dict[str, Any] = {"name": iface, "addresses": [], "is_up": False}
        if iface in stats:
            info["is_up"] = stats[iface].isup
            info["speed_mbps"] = stats[iface].speed
        if iface in io:
            info["bytes_sent"] = io[iface].bytes_sent
            info["bytes_recv"] = io[iface].bytes_recv
        for addr in addr_list:
            if addr.family.name in ("AF_INET", "AF_INET6"):
                info["addresses"].append(
                    {"family": addr.family.name, "address": addr.address, "netmask": addr.netmask}
                )
        if info["addresses"]:
            out.append(info)
    return out


def _pi_model() -> str | None:
    """Read the Raspberry Pi model string."""
    p = Path("/proc/device-tree/model")
    if p.exists():
        try:
            return p.read_text().strip().rstrip("\x00")
        except OSError:
            pass
    # Fallback: try /proc/cpuinfo
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text().splitlines():
                if line.startswith("Model"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return None


def _throttle_status() -> dict[str, Any] | None:
    """Read Pi throttle/voltage status from vcgencmd get_throttled."""
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2
        )
        if out.returncode != 0:
            return None
        # "throttled=0x0\n"
        m = re.search(r"0x([0-9a-fA-F]+)", out.stdout)
        if not m:
            return None
        val = int(m.group(1), 16)
        return {
            "raw": f"0x{val:X}",
            "under_voltage_now": bool(val & 0x1),
            "freq_capped_now": bool(val & 0x2),
            "throttled_now": bool(val & 0x4),
            "soft_temp_limit_now": bool(val & 0x8),
            "under_voltage_occurred": bool(val & 0x10000),
            "freq_capped_occurred": bool(val & 0x20000),
            "throttled_occurred": bool(val & 0x40000),
            "soft_temp_limit_occurred": bool(val & 0x80000),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _cpu_info() -> dict[str, Any]:
    """CPU core count and architecture."""
    return {
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": psutil.cpu_count(logical=True),
        "architecture": platform.machine(),
    }


def _allsky_disk_usage() -> dict[str, int]:
    """Disk usage broken down by Allsky directory."""
    p = paths()
    return {
        "images": _dir_size(p.images),
        "darks": _dir_size(p.darks),
        "keograms": _dir_size(p.keograms_dir),
        "startrails": _dir_size(p.startrails_dir),
        "videos": _dir_size(p.videos_dir),
        "config": _dir_size(p.config),
        "tmp": _dir_size(p.tmp),
    }


def _swap_info() -> dict[str, Any]:
    sw = psutil.swap_memory()
    return {"total": sw.total, "used": sw.used, "free": sw.free, "percent": sw.percent}


def system_snapshot() -> dict[str, Any]:
    """One-shot reading of system telemetry for the dashboard."""
    images_dir = paths().images
    try:
        disk_target = images_dir if images_dir.exists() else Path("/")
    except OSError:
        disk_target = Path("/")
    try:
        du = psutil.disk_usage(str(disk_target))
    except OSError:
        du = psutil.disk_usage("/")
    du_root = psutil.disk_usage("/")

    load1, load5, load15 = psutil.getloadavg()

    return {
        "boot_time": int(psutil.boot_time()),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_temp_c": cpu_temperature(),
        "cpu_info": _cpu_info(),
        "load_avg": {"1m": load1, "5m": load5, "15m": load15},
        "memory": {
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "used": psutil.virtual_memory().used,
            "percent": psutil.virtual_memory().percent,
        },
        "swap": _swap_info(),
        "disk": {
            "path": str(disk_target),
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": du.percent,
        },
        "disk_root": {
            "path": "/",
            "total": du_root.total,
            "used": du_root.used,
            "free": du_root.free,
            "percent": du_root.percent,
        },
        "pi_model": _pi_model(),
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "network": _network_info(),
        "throttle": _throttle_status(),
    }


def allsky_disk_usage() -> dict[str, int]:
    """Public accessor for Allsky directory breakdown."""
    return _allsky_disk_usage()

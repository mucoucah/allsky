"""Light install must hand latitude and longitude to capture_RPi.

Runs prepare_config on a fresh tree, then the same convertJSON.py +
filterCaptureArgs.sh pipeline allsky.sh uses. No camera is required.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PREPARE = REPO / "offload" / "pi" / "prepare_config.py"
CONVERT = REPO / "scripts" / "convertJSON.py"
FILTER = REPO / "scripts" / "filterCaptureArgs.sh"

LAT = "27.7316696"
LON = "-97.4170888"


def _tree(tmp_path: Path, settings: dict) -> Path:
    home = tmp_path / "allsky"
    (home / "config").mkdir(parents=True)
    (home / "config_repo").mkdir()
    for name in (
        "options.json",
        "RPi_cameraInfo.txt",
        "env.json",
        "autoexposure.json",
    ):
        shutil.copy(REPO / "config_repo" / f"{name}.repo", home / "config_repo" / f"{name}.repo")
    (home / "config" / "settings.json").write_text(json.dumps(settings) + "\n")
    (home / "version").write_text("test\n")
    return home


def _capture_args(home: Path) -> str:
    """Same steps as allsky.sh: convertJSON --capture-only, then filterCaptureArgs.sh."""
    env = os.environ.copy()
    env["ALLSKY_HOME"] = str(home)
    env.pop("ALLSKY_WEB_CONFIG", None)
    script = f"""
set -euo pipefail
ARGS="$("{os.environ.get('PYTHON', 'python3')}" "{CONVERT}" --capture-only)"
{{
  printf '%s\\n' "$ARGS" | "{FILTER}"
  echo "version=$(head -1 "{home}/version")"
  echo "save_dir={home}/tmp"
}}
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        env=env,
        cwd=home,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc.stdout


def _values(args: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in args.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key] = value
    return found


def test_fresh_imx290_args_include_lat_long_and_exposure(tmp_path: Path):
    home = _tree(tmp_path, {
        "cameratype": "RPi",
        "cameramodel": "imx290",
        "latitude": LAT,
        "longitude": LON,
        "angle": -6,
    })
    subprocess.run(["python3", str(PREPARE), "--home", str(home)], check=True)
    settings = json.loads((home / "config" / "settings.json").read_text())
    assert settings["latitude"] == LAT
    assert settings["longitude"] == LON
    assert settings["angle"] == -6
    assert settings["cameramodel"] == "imx290 60.00 fps"
    assert settings["nightexposure"] == 8000
    assert settings["nightgain"] == 16
    link = home / "config" / "settings_RPi_imx290_60.00_fps.json"
    assert link.is_file()
    assert link.stat().st_ino == (home / "config" / "settings.json").stat().st_ino
    assert not (home / "config" / "settings_RPi_imx290.json").exists()
    assert (home / "config" / "options.json").is_file()
    assert (home / "config" / "options.json").stat().st_size > 10_000

    args = _capture_args(home)
    values = _values(args)
    assert values["latitude"] == LAT
    assert values["longitude"] == LON
    assert values["nightexposure"] == "8000"
    assert values["nightgain"] == "16"
    assert values["angle"] in {"-6", "-6.0"}
    # Camera model is passed on the capture command line, not in the config file.
    assert "cameramodel=" not in args
    assert settings["cameramodel"] == "imx290 60.00 fps"


def test_upgrade_from_mode_string_keeps_user_values_and_relinks(tmp_path: Path):
    home = _tree(tmp_path, {
        "cameratype": "RPi",
        "cameramodel": "imx290 60.00 fps",
        "latitude": LAT,
        "longitude": LON,
        "angle": -6,
        "nightexposure": 9000,
        "nightgain": 12,
    })
    settings_path = home / "config" / "settings.json"
    stale = home / "config" / "settings_RPi_imx290.json"
    os.link(settings_path, stale)

    subprocess.run(["python3", str(PREPARE), "--home", str(home)], check=True)
    settings = json.loads(settings_path.read_text())
    assert settings["cameramodel"] == "imx290 60.00 fps"
    assert settings["latitude"] == LAT
    assert settings["longitude"] == LON
    assert settings["nightexposure"] == 9000
    assert settings["nightgain"] == 12
    link = home / "config" / "settings_RPi_imx290_60.00_fps.json"
    assert link.is_file()
    assert link.stat().st_ino == settings_path.stat().st_ino
    assert not stale.exists()

    values = _values(_capture_args(home))
    assert values["latitude"] == LAT
    assert values["longitude"] == LON
    assert values["nightexposure"] == "9000"
    assert values["nightgain"] == "12"


def test_install_light_chowns_config_after_prepare():
    text = (REPO / "offload" / "pi" / "install-light.sh").read_text()
    prepare_at = text.index("prepare_config.py")
    chown_at = text.index('chown -R "${REAL_USER}:${REAL_GROUP}" "${ALLSKY_HOME}/config"')
    assert prepare_at < chown_at


def _build_capture_rpi(home: Path) -> Path | None:
    """Compile capture_RPi when OpenCV and a C++ compiler are available."""
    if shutil.which("g++") is None or shutil.which("pkg-config") is None:
        return None
    opencv = subprocess.run(
        ["pkg-config", "--exists", "opencv4"],
        check=False,
    )
    if opencv.returncode != 0:
        opencv = subprocess.run(["pkg-config", "--exists", "opencv"], check=False)
    if opencv.returncode != 0:
        return None
    header = REPO / "src" / "include" / "allsky_common.h"
    repo_header = REPO / "src" / "include" / "allsky_common.h.repo"
    generated = False
    if not header.exists():
        text = repo_header.read_text()
        text = (
            text.replace("XX_ALLSKY_HOME_XX", str(home))
            .replace("XX_CONNECTED_CAMERAS_FILE_XX", str(home / "config" / "connected_cameras.txt"))
            .replace("XX_RPI_CAMERA_INFO_FILE_XX", str(home / "config" / "RPi_cameraInfo.txt"))
        )
        header.write_text(text)
        generated = True
    built = subprocess.run(
        ["make", "-C", str(REPO / "src"), "capture_RPi"],
        text=True,
        capture_output=True,
        check=False,
    )
    if generated:
        header.unlink(missing_ok=True)
    binary = REPO / "src" / "capture_RPi"
    if built.returncode != 0 or not binary.is_file():
        return None
    return binary


def test_check_args_binary_accepts_latitude(tmp_path: Path):
    home = _tree(tmp_path, {
        "cameratype": "RPi",
        "cameramodel": "imx290",
        "latitude": LAT,
        "longitude": LON,
        "angle": -6,
    })
    subprocess.run(["python3", str(PREPARE), "--home", str(home)], check=True)
    binary = _build_capture_rpi(home)
    if binary is None:
        pytest.skip("OpenCV is not installed; capture_RPi was not built")
    args_text = _capture_args(home)
    args_file = home / "capture_args.txt"
    args_file.write_text(args_text)
    settings = json.loads((home / "config" / "settings.json").read_text())
    proc = subprocess.run(
        [
            str(binary),
            "--check-args",
            "-cameramodel", settings["cameramodel"],
            "-cameranumber", "0",
            "-config", str(args_file),
        ],
        env={"ALLSKY_HOME": str(home), "PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert "not specified" not in combined, combined
    assert proc.returncode == 0, combined
    # validateLatitudeLongitude rewrites a signed number as digits plus N/S/E/W.
    assert "latitude=27.7316696N" in combined
    assert "longitude=97.4170888W" in combined
    assert "nightexposure_ms=8000.0000" in combined
    assert "nightgain=16.0000" in combined
    assert "cameramodel=imx290 60.00 fps" in combined

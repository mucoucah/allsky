"""Parser for rpicam-apps 1.15 --list-cameras output.

allsky.sh feeds `rpicam-still --list-cameras` (stdout and stderr) to
scripts/utilities/parseRPiCameraList.awk. Trixie prints a header, a dashed
rule, and indented mode lines; older output was just the camera line.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

AWK = Path(__file__).resolve().parents[2] / "scripts" / "utilities" / "parseRPiCameraList.awk"

# What `rpicam-hello --list-cameras` prints on rpicam-apps 1.15 (Pi OS Trixie)
# for an IMX462 that libcamera reports as imx290. Includes the header, mode
# lines, an unindented resolution (some builds), and a stderr log line.
TRIXIE_1_15 = """\
[0:01:02.345] [99] INFO Camera camera_manager.cpp:1 starting
Available cameras
-----------------
0 : imx290 [1920x1080 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx290@1a)
    Modes: 'SRGGB12_CSI2P' : 1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
                             1280x720 [120.10 fps - (320, 180)/1280x720 crop]
           'SRGGB10_CSI2P' : 1920x1080 [90.00 fps - (0, 0)/1920x1080 crop]
1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
ERROR: *** failed to generate capture configuration ***
"""

OLDER = """\
0 : imx477 [4056x3040] (/base/soc/i2c0mux/i2c@1/imx477@1a)
    Modes: 'SRGGB12_CSI2P' : 2028x1080 [50.03 fps - (0, 440)/4056x2160 crop]
                             4056x3040 [10.00 fps - (0, 0)/4056x3040 crop]
"""

TWO = """\
Available cameras
-----------------
  0 : imx290 [1920x1080 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx290@1a)
    Modes: 'SRGGB12_CSI2P' : 1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
  1 : imx477 [4056x3040 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx477@1a)
    Modes: 'SRGGB12_CSI2P' : 4056x3040 [10.00 fps - (0, 0)/4056x3040 crop]
"""


def _parse(text: str) -> list[str]:
    proc = subprocess.run(
        ["gawk", "-f", str(AWK)],
        input=text,
        text=True,
        capture_output=True,
        check=True,
    )
    assert proc.stderr == ""
    return [line for line in proc.stdout.splitlines() if line]


def test_trixie_1_15_lists_imx290_and_ignores_modes():
    assert _parse(TRIXIE_1_15) == ["RPi\t0\timx290"]


def test_older_list_cameras_format():
    assert _parse(OLDER) == ["RPi\t0\timx477"]


def test_leading_space_and_second_camera():
    assert _parse(TWO) == ["RPi\t0\timx290", "RPi\t1\timx477"]


def test_no_cameras_is_empty():
    assert _parse("No cameras available!\n") == []


def test_sensor_token_treats_mode_string_as_imx290():
    """allsky.sh compares this token, not the whole cameramodel string."""
    script = r"""
source scripts/functions.sh
camera_sensor_token "imx290 60.00 fps"
camera_sensor_token "IMX462"
camera_sensor_token "HQ"
if camera_models_match RPi "imx290 60.00 fps" "imx290"; then echo match-mode; fi
if camera_models_match RPi "imx462" "imx290"; then echo match-462; fi
if camera_models_match RPi "HQ" "imx477"; then echo match-hq; else echo differ-hq; fi
if camera_models_match ZWO "ASI290MM" "ASI290MC"; then echo match-zwo; else echo differ-zwo; fi
"""
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    assert proc.stdout.splitlines() == [
        "imx290",
        "imx290",
        "hq",
        "match-mode",
        "match-462",
        "differ-hq",
        "differ-zwo",
    ]

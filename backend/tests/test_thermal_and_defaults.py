"""Thermal guard state machine and the IMX462 night defaults."""
from __future__ import annotations

from app.allsky.settings import PLACEHOLDER_DEFAULTS, PLACEHOLDER_MAXES
from app.allsky.thermal import (
    DEFAULTS,
    decide_state,
    format_guard_line,
    guard_actions,
    validate_config,
)
from app.config import get_settings
from app.routers.auth import auth_required


def test_warm_stop_and_resume_hysteresis():
    assert decide_state("ok", 69, warn_c=70, stop_c=80, resume_c=65) == "ok"
    assert decide_state("ok", 70, warn_c=70, stop_c=80, resume_c=65) == "warm"
    assert decide_state("warm", 79, warn_c=70, stop_c=80, resume_c=65) == "warm"
    assert decide_state("warm", 80, warn_c=70, stop_c=80, resume_c=65) == "stopped"
    # Stay stopped through the warm band until the resume threshold.
    # resume_c is below warn_c, so the first cool reading is "ok".
    assert decide_state("stopped", 72, warn_c=70, stop_c=80, resume_c=65) == "stopped"
    assert decide_state("stopped", 66, warn_c=70, stop_c=80, resume_c=65) == "stopped"
    assert decide_state("stopped", 65, warn_c=70, stop_c=80, resume_c=65) == "ok"
    assert decide_state("warm", None, warn_c=70, stop_c=80, resume_c=65) == "warm"


def test_guard_file_line_and_actions():
    assert format_guard_line("warm", 15000, True) == "warm 15000 1\n"
    assert format_guard_line("ok", 0, False) == "ok 0 0\n"
    extra, skip = guard_actions("warm", 15000)
    assert (extra, skip) == (15000, True)
    extra, skip = guard_actions("stopped", 15000)
    assert (extra, skip) == (0, True)
    extra, skip = guard_actions("ok", 15000)
    assert (extra, skip) == (0, False)


def test_default_thresholds_are_valid():
    assert validate_config(DEFAULTS) == []
    bad = dict(DEFAULTS)
    bad["resume_c"] = 75
    assert validate_config(bad)


def test_imx462_night_defaults_stay_inside_analogue_gain():
    # Exposure and delay are milliseconds. 8000 ms = 8 s, 10000 ms = 10 s.
    assert PLACEHOLDER_DEFAULTS["nightexposure"] == 8_000
    assert PLACEHOLDER_DEFAULTS["nightmaxautoexposure"] == 10_000
    assert PLACEHOLDER_DEFAULTS["nightdelay"] == 500
    assert 0 <= PLACEHOLDER_DEFAULTS["nightdelay"] <= 1_000
    assert PLACEHOLDER_DEFAULTS["timelapsewidth"] == 1920
    # IMX462 analogue ceiling is ~29.51x. Defaults and the UI max stay under it.
    assert PLACEHOLDER_DEFAULTS["nightgain"] == 16
    assert PLACEHOLDER_DEFAULTS["nightmaxautogain"] == 29
    assert PLACEHOLDER_DEFAULTS["nightgain"] <= 29.51
    assert PLACEHOLDER_MAXES["nightgain"] <= 29.51
    assert PLACEHOLDER_MAXES["nightmaxautogain"] <= 29.51


def test_auth_requires_a_hash_and_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ALLSKY_WEB_AUTH", "1")
    monkeypatch.setenv("ALLSKY_WEB_USER", "admin")
    monkeypatch.setenv("ALLSKY_WEB_PASS_HASH", "")
    get_settings.cache_clear()
    assert auth_required() is False

    monkeypatch.setenv("ALLSKY_WEB_PASS_HASH", "$2b$12$examplehash")
    get_settings.cache_clear()
    assert auth_required() is True

    monkeypatch.setenv("ALLSKY_WEB_AUTH", "0")
    get_settings.cache_clear()
    assert auth_required() is False
    get_settings.cache_clear()

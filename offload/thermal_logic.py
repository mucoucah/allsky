"""Thermal state machine for the light client.

Same rules as backend/app/allsky/thermal.py: once capture is stopped it stays
stopped until the CPU is back at or below resume_c. A resume that is still at
or above warn_c lands on "warm".
"""
from __future__ import annotations


def decide_state(
    previous: str,
    temp_c: float | None,
    *,
    warn_c: float,
    stop_c: float,
    resume_c: float,
) -> str:
    if temp_c is None:
        return previous if previous in ("ok", "warm", "stopped") else "ok"
    if previous == "stopped":
        if temp_c > resume_c:
            return "stopped"
        if temp_c >= warn_c:
            return "warm"
        return "ok"
    if temp_c >= stop_c:
        return "stopped"
    if temp_c >= warn_c:
        return "warm"
    return "ok"


def format_guard_line(state: str, extra_delay_ms: int, skip_processing: bool) -> str:
    skip = 1 if skip_processing else 0
    return f"{state} {int(extra_delay_ms)} {skip}\n"


def guard_actions(state: str, warm_extra_delay_ms: int) -> tuple[int, bool]:
    if state == "warm":
        return max(0, int(warm_extra_delay_ms)), True
    if state == "stopped":
        return 0, True
    return 0, False

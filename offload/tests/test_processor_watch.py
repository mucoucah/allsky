"""Processor watch, dispatch order, end-of-night, and retention."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from offload.frames import FrameRef
from offload.processor.encode import encoder_args, parse_encoders, timelapse_command
from offload.processor.retention import dates_over_budget, expired_dates
from offload.processor.watch import BookState, dispatch_order, due_nights, ready_names
from offload.processor.service import process_batch
from offload.thermal_logic import decide_state as light_decide


def _frame(name: str, period: str, bucket: str, stamp: str) -> FrameRef:
    return FrameRef(path=Path(name), period=period, bucket=bucket, stamp=stamp, size=10)


def test_ready_names_wait_for_a_stable_size():
    previous = {"N_20261117_20261117_220000.jpg": 100, "growing.jpg": 50}
    current = {
        "N_20261117_20261117_220000.jpg": 100,
        "growing.jpg": 80,
        ".rsync-partial": 10,
        "empty.jpg": 0,
    }
    assert ready_names(previous, current) == ["N_20261117_20261117_220000.jpg"]


def test_dispatch_sends_night_frames_first():
    frames = [
        _frame("d.jpg", "D", "20261118", "20261118080000"),
        _frame("n2.jpg", "N", "20261117", "20261118010000"),
        _frame("n1.jpg", "N", "20261117", "20261117220000"),
    ]
    ordered = dispatch_order(frames, night_priority=True)
    assert [frame.name for frame in ordered] == ["n1.jpg", "n2.jpg", "d.jpg"]


def test_due_nights_quiet_and_rollover():
    state = BookState()
    state.note(_frame("n.jpg", "N", "20261117", "20261117230000"), epoch=1_000)
    assert due_nights(state, 1_100, quiet_with_day_seconds=300, quiet_alone_seconds=2700) == []
    state.note(_frame("d.jpg", "D", "20261118", "20261118070000"), epoch=1_200)
    assert due_nights(state, 1_200, quiet_with_day_seconds=300, quiet_alone_seconds=2700) == []
    assert due_nights(state, 1_600, quiet_with_day_seconds=300, quiet_alone_seconds=2700) == ["20261117"]
    state.open_nights.clear()
    state.finalized.clear()
    state.note(_frame("n.jpg", "N", "20261117", "20261117230000"), epoch=1_000)
    assert due_nights(state, 4_000, quiet_with_day_seconds=300, quiet_alone_seconds=2700) == ["20261117"]
    state.open_nights.clear()
    state.note(_frame("a.jpg", "N", "20261117", "20261117230000"), epoch=1_000)
    state.note(_frame("b.jpg", "N", "20261118", "20261118230000"), epoch=2_000)
    assert due_nights(state, 2_000, quiet_with_day_seconds=300, quiet_alone_seconds=2700) == ["20261117"]


def test_process_batch_detects_night_and_finalizes(tmp_path: Path):
    night = _frame(str(tmp_path / "n.jpg"), "N", "20261117", "20261117220000")
    day = _frame(str(tmp_path / "d.jpg"), "D", "20261118", "20261118080000")
    seen: list[str] = []
    archived: list[str] = []
    finals: list[str] = []
    state = BookState()
    process_batch(
        [day, night],
        state,
        now_epoch=1_000,
        quiet_with_day_seconds=300,
        quiet_alone_seconds=2700,
        night_priority=True,
        on_night=lambda frame: seen.append(frame.name),
        on_archive=lambda frame: archived.append(frame.name),
        on_finalize=lambda date: finals.append(date),
    )
    assert seen == ["n.jpg"]
    assert archived == ["n.jpg", "d.jpg"]
    assert finals == []
    process_batch(
        [],
        state,
        now_epoch=1_400,
        quiet_with_day_seconds=300,
        quiet_alone_seconds=2700,
        night_priority=True,
        on_night=lambda frame: seen.append(frame.name),
        on_archive=lambda frame: archived.append(frame.name),
        on_finalize=lambda date: finals.append(date),
    )
    assert finals == ["20261117"]
    assert "20261117" in state.finalized


def test_encoder_prefers_nvenc_and_falls_back():
    text = " V....D h264_nvenc NVIDIA NVENC H.264\n V....D hevc_nvenc NVIDIA\n V..... libx264 libx264 H.264\n"
    available = parse_encoders(text)
    assert encoder_args("auto", available)[:2] == ["-c:v", "h264_nvenc"]
    assert encoder_args("hevc_nvenc", available)[1] == "hevc_nvenc"
    assert encoder_args("auto", set())[1] == "libx264"
    assert encoder_args("h264_nvenc", {"libx264"})[1] == "libx264"
    cmd = timelapse_command("list.txt", "out.mp4", ["-c:v", "libx264"])
    assert cmd[0] == "ffmpeg"
    assert "out.mp4" in cmd


def test_retention_by_age_and_bytes():
    today = datetime(2026, 11, 17)
    dates = ["20261001", "20261101", "20261116", "20261117"]
    assert expired_dates(dates, today, 14) == ["20261001", "20261101"]
    sizes = {"20261115": 500, "20261116": 500, "20261117": 500}
    assert dates_over_budget(["20261115", "20261116", "20261117"], sizes, 800) == [
        "20261115", "20261116",
    ]
    assert dates_over_budget(["20261117"], sizes, 10) == []


def test_light_thermal_matches_backend_guard():
    import sys
    repo = Path(__file__).resolve().parents[2]
    backend = str(repo / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.allsky.thermal import decide_state as backend_decide

    previous = "ok"
    for temp in (None, 60, 70, 75, 80, 90, 66, 64, 70, 50):
        light = light_decide(previous, temp, warn_c=70, stop_c=80, resume_c=65)
        other = backend_decide(previous, temp, warn_c=70, stop_c=80, resume_c=65)
        assert light == other
        previous = light

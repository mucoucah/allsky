"""Low-disk guard: detect and publish the live frame, do not store raw frames."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from offload.config import from_dict
from offload.processor.disk_guard import guard_is_active
from offload.processor.service import Processor


def _cfg(tmp_path: Path, **processor):
    data = {
        "processor": {
            "incoming_dir": str(tmp_path / "incoming"),
            "data_dir": str(tmp_path / "data"),
            "raw_retention_days": 14,
            "min_free_gb": 10,
            "retention_days": 14,
        }
    }
    data["processor"].update(processor)
    return from_dict(data)


def _ready(proc: Processor, name: str, payload: bytes) -> Path:
    incoming = Path(proc.cfg.processor.incoming_dir)
    incoming.mkdir(parents=True, exist_ok=True)
    path = incoming / name
    path.write_bytes(payload)
    proc.previous_sizes[name] = path.stat().st_size
    return path


def _stub_detector(proc: Processor, seen: list[str]) -> None:
    def feed(path, _when, dest, _mask):
        assert Path(path).is_file()
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "meteor_hit.jpg").write_bytes(Path(path).read_bytes())
        seen.append(Path(path).name)

    proc.detector.feed = feed


def test_guard_thresholds():
    assert guard_is_active(False, 9.9, 10) is True
    assert guard_is_active(False, 10, 10) is False
    assert guard_is_active(True, 11.9, 10) is True
    assert guard_is_active(True, 12, 10) is False
    assert guard_is_active(True, 0, 0) is False
    assert guard_is_active(False, None, 10) is False
    assert guard_is_active(True, None, 10) is True


def test_low_disk_skips_raw_storage_and_keeps_detection_and_live_image(tmp_path: Path, monkeypatch, caplog):
    proc = Processor(_cfg(tmp_path))
    proc._last_retention = time.monotonic()
    seen: list[str] = []
    _stub_detector(proc, seen)
    night = _ready(proc, "N_20261117_20261117_220000.jpg", b"night")
    day = _ready(proc, "D_20261118_20261118_080000.jpg", b"day")
    monkeypatch.setattr("offload.processor.service.disk_free_gb", lambda _path: 4.0)

    with caplog.at_level(logging.INFO, logger="allsky-processor"):
        first = proc.step(now_epoch=1_000)
        second_night = _ready(proc, "N_20261117_20261117_220100.jpg", b"later")
        second = proc.step(now_epoch=2_000)

    data = tmp_path / "data"
    assert first["disk_guard"] is True
    assert second["disk_guard"] is True
    assert seen == [
        "N_20261117_20261117_220000.jpg",
        "D_20261118_20261118_080000.jpg",
        "N_20261117_20261117_220100.jpg",
    ]
    assert not night.exists()
    assert not day.exists()
    assert not second_night.exists()
    assert not (data / "images").exists()
    assert (data / "tmp" / "image.jpg").read_bytes() == b"later"
    assert (data / "html" / "allsky" / "meteors" / "20261118" / "meteor_hit.jpg").read_bytes() == b"day"
    state = json.loads((data / "config" / "processor_state.json").read_text())
    assert state["disk_guard"]["active"] is True
    assert state["disk_guard"]["free_gb"] == 4.0
    assert state["disk_guard"]["since"]
    assert state["finalized"] == []
    warnings = [record.message for record in caplog.records if "disk guard active" in record.message]
    assert len(warnings) == 1
    assert state["disk_guard"]["since"] in (data / "config" / "processor_state.json").read_text()


def test_guard_trips_retention_immediately_and_resumes_with_hysteresis(tmp_path: Path, monkeypatch, caplog):
    proc = Processor(_cfg(tmp_path))
    proc._last_retention = time.monotonic()
    old = tmp_path / "data" / "images" / "20200101" / "N_20200101_20200101_010101.jpg"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"stale")
    free = {"gb": 3.0}
    monkeypatch.setattr("offload.processor.service.disk_free_gb", lambda _path: free["gb"])

    with caplog.at_level(logging.INFO, logger="allsky-processor"):
        proc.step(now_epoch=1_000)
        assert not old.exists()
        proc.step(now_epoch=2_000)
        free["gb"] = 11.5
        held = proc.step(now_epoch=3_000)
        free["gb"] = 12.0
        cleared = proc.step(now_epoch=4_000)

    assert held["disk_guard"] is True
    assert cleared["disk_guard"] is False
    state = json.loads((tmp_path / "data" / "config" / "processor_state.json").read_text())
    assert state["disk_guard"]["active"] is False
    assert state["disk_guard"]["since"]
    assert len([record for record in caplog.records if "disk guard active" in record.message]) == 1
    assert len([record for record in caplog.records if "disk guard cleared" in record.message]) == 1


def test_restart_does_not_alert_again_and_hourly_retention_is_scheduled(tmp_path: Path, monkeypatch, caplog):
    data = tmp_path / "data"
    since = "2026-11-18T01:00:00+00:00"
    state_path = data / "config" / "processor_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "finalized": ["20261101"],
        "disk_guard": {"active": True, "free_gb": 4.0, "since": since},
    }))
    proc = Processor(_cfg(tmp_path))
    assert proc.guard_active is True
    assert proc.guard_since == since
    monkeypatch.setattr("offload.processor.service.disk_free_gb", lambda _path: 4.0)
    old = data / "images" / "20200101" / "D_20200101_20200101_080000.jpg"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")

    with caplog.at_level(logging.WARNING, logger="allsky-processor"):
        proc._last_retention = time.monotonic()
        proc.step(now_epoch=1_000)
        assert old.exists()
        proc._last_retention = time.monotonic() - proc.retention_interval - 1
        proc.step(now_epoch=2_000)

    assert not old.exists()
    assert not any("disk guard active" in record.message for record in caplog.records)
    saved = json.loads(state_path.read_text())
    assert saved["disk_guard"]["since"] == since
    assert saved["finalized"] == ["20261101"]


def test_healthy_disk_stores_raw_frames_and_detects_night_only(tmp_path: Path, monkeypatch):
    proc = Processor(_cfg(tmp_path))
    proc._last_retention = time.monotonic()
    seen: list[str] = []
    _stub_detector(proc, seen)
    _ready(proc, "D_20261118_20261118_080000.jpg", b"day")
    night = _ready(proc, "N_20261117_20261117_220000.jpg", b"night")
    monkeypatch.setattr("offload.processor.service.disk_free_gb", lambda _path: 40.0)

    report = proc.step(now_epoch=1_000)

    data = tmp_path / "data"
    assert report["disk_guard"] is False
    assert seen == ["N_20261117_20261117_220000.jpg"]
    assert not night.exists()
    stored = data / "images" / "20261117" / night.name
    assert stored.read_bytes() == b"night"
    assert (data / "images" / "20261118" / "D_20261118_20261118_080000.jpg").read_bytes() == b"day"
    assert (data / "tmp" / "image.jpg").read_bytes() == b"day"
    assert not (data / "config" / "processor_state.json").exists() or "disk_guard" not in json.loads(
        (data / "config" / "processor_state.json").read_text()
    )

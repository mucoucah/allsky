"""Sync agent buffering, cap, and delete-after-confirm."""
from __future__ import annotations

import json
from pathlib import Path

from offload.config import OffloadConfig, RemoteConfig, from_dict, merge_push, save_config
from offload.frames import choose_deletions, frame_name, parse_frame_name, upload_plan
from offload.heartbeat import build_status, last_camera_error, parse_throttled
from offload.mode import apply_quality
from offload.settings_pull import apply_pulled
from offload.sync import (
    CycleResult,
    TransferRunner,
    apply_confirmed,
    backoff_seconds,
    bandwidth_kib_per_s,
    build_rsync_upload,
    cycle,
    enforce_cap,
)
from offload.frames import FrameRef
from datetime import datetime


def _touch(outbox: Path, name: str, size: int) -> None:
    path = outbox / name
    path.write_bytes(b"x" * size)


def _cfg(outbox: Path, **kwargs) -> OffloadConfig:
    cfg = OffloadConfig(mode="capture-only", outbox_dir=str(outbox), outbox_max_bytes=1000)
    for key, value in kwargs.items():
        setattr(cfg, key, value)
    cfg.remote = RemoteConfig(host="pc.local", user="allsky", ssh_key="/tmp/id", bandwidth_limit_kbps=1600, port=2222)
    return cfg


class FakeRunner(TransferRunner):
    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.uploads: list[list[str]] = []
        self.status = 0
        self.pulled = 0

    def upload(self, frames, *, remove_source: bool) -> bool:
        names = [frame.name for frame in frames]
        self.uploads.append(names)
        if self.fail_on == "frames":
            return False
        if remove_source:
            for frame in frames:
                frame.path.unlink(missing_ok=True)
        return True

    def upload_status(self, path: Path) -> bool:
        self.status += 1
        return self.fail_on != "status"

    def pull(self, dest: Path) -> bool:
        self.pulled += 1
        return True


def test_backoff_and_bandwidth():
    assert backoff_seconds(1) == 5
    assert backoff_seconds(2) == 10
    assert backoff_seconds(3) == 20
    assert backoff_seconds(10) == 300
    assert bandwidth_kib_per_s(0) == 0
    assert bandwidth_kib_per_s(1600) == 200
    assert bandwidth_kib_per_s(4) == 1


def test_frame_names_round_trip():
    when = datetime(2026, 11, 18, 1, 30, 15)
    name = frame_name(when, "NIGHT")
    assert name == "N_20261117_20261118_013015.jpg"
    parsed = parse_frame_name(name)
    assert parsed == ("N", "20261117", "20261118013015")
    day = frame_name(datetime(2026, 11, 18, 14, 0, 0), "DAY")
    assert day.startswith("D_20261118_")


def test_cap_deletes_day_frames_before_night(tmp_path: Path):
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    _touch(outbox, "D_20261117_20261117_120000.jpg", 400)
    _touch(outbox, "D_20261117_20261117_130000.jpg", 400)
    _touch(outbox, "N_20261117_20261117_220000.jpg", 400)
    _touch(outbox, "N_20261117_20261117_230000.jpg", 400)
    from offload.frames import list_frames
    victims = choose_deletions(list_frames(outbox), 900, night_priority=True)
    assert [item.name for item in victims] == [
        "D_20261117_20261117_120000.jpg",
        "D_20261117_20261117_130000.jpg",
    ]
    removed, warning = enforce_cap(outbox, _cfg(outbox, outbox_max_bytes=900))
    assert "outbox over cap" in warning
    assert removed == [item.name for item in victims]
    left = sorted(path.name for path in outbox.iterdir())
    assert left == [
        "N_20261117_20261117_220000.jpg",
        "N_20261117_20261117_230000.jpg",
    ]


def test_upload_keeps_files_until_confirm(tmp_path: Path):
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    _touch(outbox, "N_20261117_20261117_220000.jpg", 10)
    _touch(outbox, "D_20261117_20261117_120000.jpg", 10)
    status = tmp_path / "pi-status.json"
    status.write_text("{}")
    runner = FakeRunner(fail_on="frames")
    result = cycle(_cfg(outbox, outbox_max_bytes=10_000), outbox, runner, status)
    assert result.ok is False
    assert sorted(path.name for path in outbox.iterdir()) == [
        "D_20261117_20261117_120000.jpg",
        "N_20261117_20261117_220000.jpg",
    ]
    runner.fail_on = None
    runner.uploads.clear()
    result = cycle(_cfg(outbox, outbox_max_bytes=10_000), outbox, runner, status)
    assert result.ok is True
    assert result.uploaded_night == ["N_20261117_20261117_220000.jpg"]
    assert result.uploaded_day == ["D_20261117_20261117_120000.jpg"]
    assert runner.uploads[0] == ["N_20261117_20261117_220000.jpg"]
    assert runner.uploads[1] == ["D_20261117_20261117_120000.jpg"]
    assert list(outbox.iterdir()) == []


def test_drop_day_frames_are_not_uploaded(tmp_path: Path):
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    _touch(outbox, "N_20261117_20261117_220000.jpg", 10)
    _touch(outbox, "D_20261117_20261117_120000.jpg", 10)
    status = tmp_path / "pi-status.json"
    status.write_text("{}")
    cfg = _cfg(outbox, outbox_max_bytes=10_000)
    cfg.drop_day_frames = True
    runner = FakeRunner()
    result = cycle(cfg, outbox, runner, status)
    assert result.dropped_day == ["D_20261117_20261117_120000.jpg"]
    assert runner.uploads == [["N_20261117_20261117_220000.jpg"]]
    assert list(outbox.iterdir()) == []


def test_apply_confirmed_ignores_failed_batch(tmp_path: Path):
    path = tmp_path / "N_20261117_20261117_220000.jpg"
    path.write_bytes(b"abc")
    frame = FrameRef(path=path, period="N", bucket="20261117", stamp="20261117220000", size=3)
    assert apply_confirmed([frame], {path.name}, ok=False) == []
    assert path.exists()
    assert apply_confirmed([frame], {path.name}, ok=True) == [path.name]
    assert not path.exists()


def test_rsync_command_is_resumable_and_limited():
    remote = RemoteConfig(
        host="192.168.1.20",
        port=2222,
        user="allsky",
        path="/srv/allsky/incoming",
        ssh_key="/home/pi/.ssh/allsky_offload",
        bandwidth_limit_kbps=800,
    )
    cmd = build_rsync_upload(remote, Path("/tmp/list"), remove_source=True)
    text = " ".join(cmd)
    assert "--partial" in cmd
    assert "--append-verify" in cmd
    assert "--remove-source-files" in cmd
    assert "--bwlimit" in cmd
    assert "100" in cmd  # 800 kbps -> 100 KiB/s
    assert "BatchMode=yes" in text
    assert "allsky@192.168.1.20:/srv/allsky/incoming/" in cmd[-1]


def test_settings_pull_restarts_only_when_changed(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    dest = tmp_path / "settings.json"
    dest.write_text('{"nightexposure": 8000}\n')
    offload = tmp_path / "offload.json"
    save_config(OffloadConfig(mode="capture-only", remote=RemoteConfig(ssh_key="/secret")), offload)
    (staging / "settings.json").write_text('{"nightexposure": 8000}\n')
    assert apply_pulled(staging, dest, offload) is False
    (staging / "settings.json").write_text('{"nightexposure": 9000}\n')
    (staging / "offload-push.json").write_text(json.dumps({
        "jpeg_quality": 85,
        "ssh_key": "nope",
        "bandwidth_limit_kbps": 500,
    }))
    assert apply_pulled(staging, dest, offload) is True
    saved = json.loads(offload.read_text())
    assert saved["jpeg_quality"] == 85
    assert saved["remote"]["bandwidth_limit_kbps"] == 500
    assert saved["remote"]["ssh_key"] == "/secret"


def test_merge_push_does_not_clear_ssh_key():
    cfg = OffloadConfig(remote=RemoteConfig(host="pc", ssh_key="/key"))
    cfg, changed = merge_push(cfg, {"host": "other", "ssh_key": "", "jpeg_quality": 90})
    assert cfg.remote.host == "pc"
    assert cfg.remote.ssh_key == "/key"
    assert changed is False


def test_apply_quality_rewrites_capture_args(tmp_path: Path):
    args = tmp_path / "args.txt"
    args.write_text("filename=image.jpg\nquality=100\n")
    apply_quality(args, 90)
    text = args.read_text().splitlines()
    assert text.count("quality=90") == 1
    assert "quality=100" not in text


def test_heartbeat_shape():
    status = build_status(
        temp_c=54.2,
        throttled_text="throttled=0x50005",
        disk={"path": "/var", "total": 100, "used": 40, "free": 60, "percent": 40.0},
        outbox_bytes=20,
        outbox_files=2,
        last_frame_time="2026-11-17T22:00:00",
        last_frame_name="N_20261117_20261117_220000.jpg",
        camera_error=last_camera_error("info\nERROR: capture failed on rpicam\n"),
        thermal_state="warm",
        mode="capture-only",
        hostname="pi",
    )
    assert status["temp_c"] == 54.2
    assert status["throttled"]["throttled_now"] is True
    assert status["camera_error"].endswith("rpicam")
    bits = parse_throttled("throttled=0x0")
    assert bits["any_now"] is False


def test_upload_plan_night_first():
    frames = [
        FrameRef(Path("d.jpg"), "D", "20261117", "20261117120000", 1),
        FrameRef(Path("n.jpg"), "N", "20261117", "20261117220000", 1),
    ]
    first, second, drop = upload_plan(frames, night_priority=True, drop_day_frames=False)
    assert [item.period for item in first] == ["N"]
    assert [item.period for item in second] == ["D"]
    assert drop == []


def test_from_dict_defaults_to_normal():
    assert from_dict({}).mode == "normal"
    assert from_dict({"mode": "capture-only"}).capture_only is True
    assert isinstance(CycleResult(ok=True).uploaded_night, list)

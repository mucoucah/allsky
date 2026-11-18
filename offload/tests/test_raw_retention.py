"""Raw-frame retention keeps every product type and preserves meteor frames."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from offload.config import from_dict, validate_config
from offload.processor.retention import prune_raw_frames
from offload.processor.service import apply_retention

TODAY = datetime(2026, 11, 18)
OLD = "20261101"
EDGE = "20261104"  # exactly raw_retention_days old; kept
RECENT = "20261117"


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _build_tree(root: Path) -> dict[str, bytes]:
    """Return payloads of files the prune must delete, keyed by relative path."""
    doomed = {
        f"images/{OLD}/N_20261101_20261101_220000.jpg": b"night-raw",
        f"images/{OLD}/N_20261101_20261101_220000.json": b'{"exposure": 8}',
        f"images/{OLD}/N_20261101_20261101_220000.txt": b"sidecar",
        f"images/{OLD}/N_20261101_20261101_220000.xml": b"<x/>",
        f"images/{OLD}/N_20261101_20261101_220000.xmp": b"<xmp/>",
        f"images/{OLD}/thumbnails/N_20261101_20261101_220000.jpg": b"night-thumb",
        f"images/{OLD}/D_20261101_20261101_120000.jpg": b"day-raw",
        f"images/{OLD}/thumbnails/D_20261101_20261101_120000.jpg": b"day-thumb",
        f"images/{OLD}/D_20261101_20261101_130000.jpg": b"hit-original",
        f"images/{OLD}/image-20261101230000.jpg": b"classic-jpg",
        f"images/{OLD}/image-20261101230000.png": b"classic-png",
        f"images/{OLD}/thumbnails/image-20261101230000.jpg": b"classic-thumb",
    }
    for rel, payload in doomed.items():
        _write(root / rel, payload)

    kept = {
        f"images/{OLD}/keogram/keogram-{OLD}.jpg": b"keogram",
        f"images/{OLD}/startrails/startrails-{OLD}.jpg": b"startrails",
        f"images/{OLD}/allsky-{OLD}.mp4": b"timelapse",
        f"images/{OLD}/mini-timelapse.mp4": b"mini",
        f"images/{OLD}/allsky-{OLD}.txt": b"file 'frame.jpg'\n",
        f"images/{OLD}/keogram-{OLD}.jpg": b"keogram-root",
        f"images/{OLD}/startrails-{OLD}.png": b"startrails-root",
        f"images/{OLD}/meteor_{OLD}_230000.jpg": b"hit-copy-in-day",
        f"images/{OLD}/notes.txt": b"notes",
        f"images/{OLD}/overlay.png": b"overlay",
        f"images/{OLD}/thumbnails/keogram-{OLD}.jpg": b"keogram-thumb",
        f"images/{OLD}/hits/stray.txt": b"hits-dir",
        f"images/{OLD}/meteor/N_20261101_20261101_010101.jpg": b"inside-meteor-dir",
        f"images/{OLD}/timelapse/clip.mp4": b"clip",
        f"images/{EDGE}/N_20261104_20261104_220000.jpg": b"edge-raw",
        f"images/{RECENT}/N_20261117_20261117_220000.jpg": b"recent-raw",
        f"images/{RECENT}/thumbnails/N_20261117_20261117_220000.jpg": b"recent-thumb",
        f"html/allsky/keograms/keogram-{OLD}.jpg": b"html-keogram",
        f"html/allsky/startrails/startrails-{OLD}.jpg": b"html-startrails",
        f"html/allsky/videos/allsky-{OLD}.mp4": b"html-video",
        f"html/allsky/meteors/{OLD}/meteor_{OLD}_220000.jpg": b"hit-frame",
        f"html/allsky/meteors/{OLD}/meteor_{OLD}_220000_crop.jpg": b"hit-crop",
        "tmp/image.jpg": b"live",
        "config/processor_state.json": b"{}\n",
        "darks/dark.jpg": b"dark",
    }
    for rel, payload in kept.items():
        _write(root / rel, payload)
    (root / "html" / "allsky" / "meteors" / OLD / f"meteor_{OLD}_220000.json").write_text(
        json.dumps({
            "frame": f"meteor_{OLD}_220000.jpg",
            "crop": f"meteor_{OLD}_220000_crop.jpg",
            "meteor_count": 1,
            "lines": [{"x1": 0, "y1": 0, "x2": 10, "y2": 10}],
            "raw_frame": f"images/{OLD}/N_20261101_20261101_220000.jpg",
        })
    )
    (root / "html" / "allsky" / "meteors" / OLD / "only_original.json").write_text(
        json.dumps({
            "frame": "D_20261101_20261101_130000.jpg",
            "meteor_count": 1,
            "lines": [],
        })
    )
    return doomed


def test_prune_deletes_raw_frames_and_keeps_every_product(tmp_path: Path, caplog):
    doomed = _build_tree(tmp_path)
    expected_bytes = sum(len(payload) for payload in doomed.values())
    with caplog.at_level(logging.INFO, logger="allsky-processor"):
        result = prune_raw_frames(tmp_path, today=TODAY, keep_days=14)

    assert set(result.removed) == set(doomed)
    assert result.count == len(doomed)
    assert result.bytes == expected_bytes
    assert f"raw retention removed {len(doomed)} file(s), {expected_bytes} bytes" in caplog.text

    for rel in doomed:
        assert not (tmp_path / rel).exists(), rel
    assert (tmp_path / "images" / OLD).is_dir()
    assert (tmp_path / "images" / OLD / "keogram" / f"keogram-{OLD}.jpg").read_bytes() == b"keogram"
    assert (tmp_path / "images" / OLD / "startrails" / f"startrails-{OLD}.jpg").read_bytes() == b"startrails"
    assert (tmp_path / "images" / OLD / f"allsky-{OLD}.mp4").read_bytes() == b"timelapse"
    assert (tmp_path / "images" / OLD / "mini-timelapse.mp4").read_bytes() == b"mini"
    assert (tmp_path / "images" / OLD / f"allsky-{OLD}.txt").read_bytes().startswith(b"file ")
    assert (tmp_path / "images" / OLD / f"keogram-{OLD}.jpg").read_bytes() == b"keogram-root"
    assert (tmp_path / "images" / OLD / f"startrails-{OLD}.png").read_bytes() == b"startrails-root"
    assert (tmp_path / "images" / OLD / f"meteor_{OLD}_230000.jpg").read_bytes() == b"hit-copy-in-day"
    assert (tmp_path / "images" / OLD / "notes.txt").read_bytes() == b"notes"
    assert (tmp_path / "images" / OLD / "overlay.png").read_bytes() == b"overlay"
    assert (tmp_path / "images" / OLD / "thumbnails" / f"keogram-{OLD}.jpg").read_bytes() == b"keogram-thumb"
    assert (tmp_path / "images" / OLD / "hits" / "stray.txt").read_bytes() == b"hits-dir"
    assert (tmp_path / "images" / OLD / "meteor" / "N_20261101_20261101_010101.jpg").read_bytes() == b"inside-meteor-dir"
    assert (tmp_path / "images" / OLD / "timelapse" / "clip.mp4").read_bytes() == b"clip"
    assert (tmp_path / "images" / EDGE / "N_20261104_20261104_220000.jpg").read_bytes() == b"edge-raw"
    assert (tmp_path / "images" / RECENT / "N_20261117_20261117_220000.jpg").read_bytes() == b"recent-raw"
    assert (tmp_path / "images" / RECENT / "thumbnails" / "N_20261117_20261117_220000.jpg").read_bytes() == b"recent-thumb"
    assert (tmp_path / "html" / "allsky" / "keograms" / f"keogram-{OLD}.jpg").read_bytes() == b"html-keogram"
    assert (tmp_path / "html" / "allsky" / "startrails" / f"startrails-{OLD}.jpg").read_bytes() == b"html-startrails"
    assert (tmp_path / "html" / "allsky" / "videos" / f"allsky-{OLD}.mp4").read_bytes() == b"html-video"
    hit = tmp_path / "html" / "allsky" / "meteors" / OLD
    assert (hit / f"meteor_{OLD}_220000.jpg").read_bytes() == b"hit-frame"
    assert (hit / f"meteor_{OLD}_220000_crop.jpg").read_bytes() == b"hit-crop"
    assert (hit / f"meteor_{OLD}_220000.json").is_file()
    assert (hit / "only_original.json").is_file()
    assert (hit / "N_20261101_20261101_220000.jpg").read_bytes() == b"night-raw"
    assert (hit / "D_20261101_20261101_130000.jpg").read_bytes() == b"hit-original"
    assert (tmp_path / "tmp" / "image.jpg").read_bytes() == b"live"
    assert (tmp_path / "config" / "processor_state.json").is_file()
    assert (tmp_path / "darks" / "dark.jpg").read_bytes() == b"dark"


def test_empty_day_directory_is_removed_and_products_keep_the_directory(tmp_path: Path):
    raw_only = tmp_path / "images" / "20261001" / "D_20261001_20261001_080000.jpg"
    _write(raw_only, b"gone")
    _write(tmp_path / "images" / "20261001" / "thumbnails" / raw_only.name, b"t")
    _write(tmp_path / "images" / OLD / "N_20261101_20261101_220000.jpg", b"raw")
    _write(tmp_path / "images" / OLD / "keogram" / f"keogram-{OLD}.jpg", b"keep")

    prune_raw_frames(tmp_path, today=TODAY, keep_days=14)

    assert not (tmp_path / "images" / "20261001").exists()
    assert (tmp_path / "images" / OLD).is_dir()
    assert not (tmp_path / "images" / OLD / "N_20261101_20261101_220000.jpg").exists()
    assert (tmp_path / "images" / OLD / "keogram" / f"keogram-{OLD}.jpg").read_bytes() == b"keep"


def test_referenced_frame_is_kept_when_the_hits_copy_fails(tmp_path: Path, monkeypatch):
    frame = tmp_path / "images" / OLD / "N_20261101_20261101_220000.jpg"
    _write(frame, b"only-copy")
    other = tmp_path / "images" / OLD / "D_20261101_20261101_120000.jpg"
    _write(other, b"plain")
    meta = tmp_path / "html" / "allsky" / "meteors" / OLD / "hit.json"
    _write(meta, b"")
    meta.write_text(json.dumps({"raw_frame": frame.name, "meteor_count": 1}))

    def fail_copy(*_args, **_kwargs):
        raise OSError("drvfs refused the copy")

    monkeypatch.setattr("offload.processor.retention.shutil.copy2", fail_copy)
    result = prune_raw_frames(tmp_path, today=TODAY, keep_days=14)

    assert frame.read_bytes() == b"only-copy"
    assert not other.exists()
    assert any(path.endswith(frame.name) for path in result.removed) is False


def test_symlink_raw_frame_is_unlinked_and_its_target_remains(tmp_path: Path):
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    link = tmp_path / "images" / OLD / "N_20261101_20261101_220000.jpg"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    prune_raw_frames(tmp_path, today=TODAY, keep_days=14)

    assert not link.exists()
    assert outside.read_bytes() == b"outside"


def test_zero_keep_days_deletes_nothing(tmp_path: Path):
    frame = tmp_path / "images" / OLD / "N_20261101_20261101_220000.jpg"
    _write(frame, b"stay")
    result = prune_raw_frames(tmp_path, today=TODAY, keep_days=0)
    assert result.count == 0
    assert frame.read_bytes() == b"stay"


def test_disk_budget_drops_raw_frames_and_keeps_the_keogram(tmp_path: Path):
    old = tmp_path / "images" / "20261115" / "N_20261115_20261115_220000.jpg"
    new = tmp_path / "images" / "20261117" / "N_20261117_20261117_220000.jpg"
    keogram = tmp_path / "images" / "20261115" / "keogram" / "keogram-20261115.jpg"
    _write(old, b"x" * 50)
    _write(new, b"y" * 50)
    _write(keogram, b"z" * 50)
    cfg = from_dict({
        "processor": {
            "data_dir": str(tmp_path),
            "raw_retention_days": 10000,
            "max_disk_bytes": 80,
        }
    })
    removed = apply_retention(cfg, TODAY)
    assert any(path.endswith(old.name) for path in removed)
    assert not old.exists()
    assert keogram.read_bytes() == b"z" * 50
    assert new.read_bytes() == b"y" * 50


def test_raw_retention_config_defaults_and_legacy_window():
    fresh = from_dict({})
    assert fresh.processor.raw_retention_days == 14
    assert fresh.processor.min_free_gb == 10
    legacy = from_dict({"processor": {"retention_days": 7}})
    assert legacy.processor.raw_retention_days == 7
    explicit = from_dict({"processor": {"retention_days": 7, "raw_retention_days": 30, "min_free_gb": 4}})
    assert explicit.processor.raw_retention_days == 30
    assert explicit.processor.min_free_gb == 4
    errors = validate_config({"processor": {"raw_retention_days": -1, "min_free_gb": -0.5}})
    assert any("raw_retention_days" in error for error in errors)
    assert any("min_free_gb" in error for error in errors)
    assert validate_config({"processor": {"raw_retention_days": 0, "min_free_gb": 0}}) == []

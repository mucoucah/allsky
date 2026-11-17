"""Meteor false-positive rejection on synthetic frames."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.notify.meteor import analyze, line_continues, save_hit


def _write(path: Path, gray: np.ndarray) -> None:
    # PNG so a repeated frame stays identical. JPEG noise would look like motion.
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise RuntimeError(f"failed to write {path}")


def _stars(canvas: np.ndarray) -> None:
    for x, y in ((30, 30), (80, 150), (160, 40), (120, 90)):
        cv2.circle(canvas, (x, y), 2, 220, -1)


def test_new_streak_kept_static_stars_dropped(tmp_path: Path):
    prev = np.zeros((200, 240), np.uint8)
    curr = prev.copy()
    _stars(prev)
    _stars(curr)
    cv2.line(curr, (15, 100), (210, 130), 255, 2)
    prev_path = tmp_path / "prev.png"
    curr_path = tmp_path / "curr.png"
    _write(prev_path, prev)
    _write(curr_path, curr)

    _, previous_gray, _ = analyze(prev_path, min_length=40, max_length=400, annotate=False, scale=1.0)
    result, _, _ = analyze(
        curr_path,
        min_length=40,
        max_length=400,
        annotate=False,
        scale=1.0,
        previous_gray=previous_gray,
        history=[previous_gray],
    )
    assert result.temporal_filter is True
    assert result.meteor_count >= 1


def test_identical_frames_reject_a_persistent_streak(tmp_path: Path):
    gray = np.zeros((200, 240), np.uint8)
    cv2.line(gray, (10, 40), (220, 50), 255, 2)
    path = tmp_path / "same.png"
    _write(path, gray)
    first, previous_gray, _ = analyze(path, min_length=40, max_length=400, annotate=False, scale=1.0)
    second, _, _ = analyze(
        path,
        min_length=40,
        max_length=400,
        annotate=False,
        scale=1.0,
        previous_gray=previous_gray,
        history=[previous_gray],
        previous_lines=first.candidate_lines,
    )
    assert second.meteor_count == 0


def test_mask_hides_a_streak(tmp_path: Path):
    gray = np.zeros((200, 240), np.uint8)
    cv2.line(gray, (15, 100), (210, 110), 255, 2)
    path = tmp_path / "masked.png"
    _write(path, gray)
    mask = np.zeros_like(gray)
    mask[:, :] = 255  # white = excluded
    mask_path = tmp_path / "mask.png"
    cv2.imwrite(str(mask_path), mask)
    result = analyze(path, min_length=30, max_length=400, annotate=False, scale=1.0, mask_path=mask_path)[0]
    assert result.meteor_count == 0


def test_line_continues_matches_a_moved_but_similar_streak():
    width, height = 1920, 1080
    first = (100, 200, 800, 260)
    # Same angle, midpoint still within 35% of the diagonal.
    second = (180, 230, 880, 290)
    assert line_continues(second, [first], width, height)
    # A streak on the opposite side of the frame is a different event.
    far = (1400, 800, 1800, 900)
    assert line_continues(far, [first], width, height) is False


def test_save_hit_writes_frame_crop_and_json(tmp_path: Path):
    img = np.zeros((100, 120, 3), np.uint8)
    cv2.line(img, (10, 20), (100, 80), (255, 255, 255), 2)
    payload = save_hit(img, [(10, 20, 100, 80)], tmp_path)
    assert (tmp_path / payload["frame"]).is_file()
    assert (tmp_path / payload["crop"]).is_file()
    sidecar = list(tmp_path.glob("*.json"))
    assert len(sidecar) == 1
    text = sidecar[0].read_text()
    assert '"x1": 10' in text
    assert "meteor_count" in text

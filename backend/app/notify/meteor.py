"""Meteor (falling star / streak) detection in allsky images.

The watcher runs this on every new night frame, off the asyncio event loop:
  1. Grayscale, downscaled 2x, with the user mask applied (white = excluded).
  2. Subtract the previous frame, or a short running median of recent frames,
     so stars and static edges disappear.
  3. Canny + probabilistic Hough, then the existing length and brightness
     filters.
  4. Drop a streak that is already bright on the previous frame, or that
     continues a line from the previous frame (planes and satellites).

Hit frames are saved by the watcher as a full JPEG, a crop, and a small JSON
file under html/allsky/meteors/<date>/.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

# libcamera IMX462 frames are 1920x1080. Half-scale keeps Hough cheap on a Pi 4.
DEFAULT_SCALE = 0.5
DIFF_THRESHOLD = 18


@dataclass
class MeteorResult:
    meteor_count: int = 0
    line_count: int = 0
    lines: list[tuple[int, int, int, int]] = field(default_factory=list)
    # Lines that passed length filters, in full-frame pixels, before the
    # cross-frame "this streak continued" rejection. The watcher holds these
    # for one frame so a mover can be told apart from a single-frame meteor.
    candidate_lines: list[tuple[int, int, int, int]] = field(default_factory=list)
    annotated_jpeg: bytes | None = None
    temporal_filter: bool = False


def _reference(previous: np.ndarray | None, history: list[np.ndarray] | None) -> np.ndarray | None:
    frames: list[np.ndarray] = []
    if history:
        frames.extend(history[-3:])
    elif previous is not None:
        frames.append(previous)
    if not frames:
        return None
    if len(frames) == 1:
        return frames[-1]
    stack = np.stack([f for f in frames if f.shape == frames[-1].shape], axis=0)
    if stack.shape[0] == 0:
        return None
    return np.median(stack, axis=0).astype(np.uint8)


def _line_length(x1: float, y1: float, x2: float, y2: float) -> float:
    return float(np.hypot(x2 - x1, y2 - y1))


def _angle_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def line_continues(
    line: tuple[int, int, int, int],
    previous_lines: list[tuple[int, int, int, int]],
    width: int,
    height: int,
    angle_tol: float = 12.0,
    dist_frac: float = 0.35,
) -> bool:
    """True when `line` matches a streak already seen on the previous frame."""
    if not previous_lines or width <= 0 or height <= 0:
        return False
    diag = float(np.hypot(width, height))
    ax = _angle_deg(*line)
    amx = (line[0] + line[2]) / 2.0
    amy = (line[1] + line[3]) / 2.0
    for prev in previous_lines:
        diff = abs(ax - _angle_deg(*prev))
        diff = min(diff, 180.0 - diff)
        if diff > angle_tol:
            continue
        pmx = (prev[0] + prev[2]) / 2.0
        pmy = (prev[1] + prev[3]) / 2.0
        if math.hypot(amx - pmx, amy - pmy) <= dist_frac * diag:
            return True
    return False


def _persists_on_previous(
    previous: np.ndarray, x1: int, y1: int, x2: int, y2: int,
) -> bool:
    """True when the previous frame is already bright along this segment.

    A meteor is new, so the previous frame along that line is dark sky.
    A star edge, a parked light, or a streak that lasted into this exposure
    is bright on the previous frame and is rejected.
    """
    num = max(8, int(_line_length(x1, y1, x2, y2) / 2))
    xs = np.linspace(x1, x2, num).astype(int)
    ys = np.linspace(y1, y2, num).astype(int)
    h, w = previous.shape[:2]
    xs = np.clip(xs, 0, w - 1)
    ys = np.clip(ys, 0, h - 1)
    values = previous[ys, xs].astype(float)
    return float(np.median(values)) >= 40 and float(np.mean(values)) >= 30


def _is_uniform_brightness(
    gray: np.ndarray, x1: int, y1: int, x2: int, y2: int,
    uniformity_threshold: float = 0.15,
) -> bool:
    """Satellites are even along their length. Meteors flare and fade."""
    num_samples = max(10, int(_line_length(x1, y1, x2, y2) / 3))
    xs = np.linspace(x1, x2, num_samples).astype(int)
    ys = np.linspace(y1, y2, num_samples).astype(int)
    h, w = gray.shape[:2]
    xs = np.clip(xs, 0, w - 1)
    ys = np.clip(ys, 0, h - 1)
    values = gray[ys, xs].astype(float)
    mean = float(values.mean())
    if mean < 10:
        return False
    return float(values.std() / mean) < uniformity_threshold


def _apply_mask(gray: np.ndarray, mask_path: Path | None) -> np.ndarray:
    if not mask_path or not mask_path.exists():
        return gray
    mask_img = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask_img is None:
        return gray
    if mask_img.shape != gray.shape:
        mask_img = cv2.resize(mask_img, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
    # Painted white areas are excluded.
    return cv2.bitwise_and(gray, gray, mask=cv2.bitwise_not(mask_img))


_CUDA_UNUSABLE = False


def cuda_device_count() -> int:
    cuda = getattr(cv2, "cuda", None)
    if cuda is None:
        return 0
    try:
        return int(cv2.cuda.getCudaEnabledDeviceCount())
    except Exception:
        return 0


def _gray_scaled(image_bgr: np.ndarray, scale: float, use_cuda: bool) -> np.ndarray:
    """Grayscale and optional downscale. CUDA when the build has a device."""
    global _CUDA_UNUSABLE
    if use_cuda and not _CUDA_UNUSABLE and cuda_device_count() > 0:
        try:
            gpu = cv2.cuda_GpuMat()
            gpu.upload(image_bgr)
            gray_gpu = cv2.cuda.cvtColor(gpu, cv2.COLOR_BGR2GRAY)
            if scale != 1.0:
                width = max(1, int(round(image_bgr.shape[1] * scale)))
                height = max(1, int(round(image_bgr.shape[0] * scale)))
                gray_gpu = cv2.cuda.resize(gray_gpu, (width, height), interpolation=cv2.INTER_AREA)
            return gray_gpu.download()
        except Exception:
            _CUDA_UNUSABLE = True
            log.info("meteor: CUDA grayscale unavailable, using CPU")
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    if scale != 1.0:
        gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return gray


def _canny(working: np.ndarray, use_cuda: bool) -> np.ndarray:
    global _CUDA_UNUSABLE
    image = working.astype(np.uint8)
    if use_cuda and not _CUDA_UNUSABLE and cuda_device_count() > 0:
        try:
            gpu = cv2.cuda_GpuMat()
            gpu.upload(image)
            detector = cv2.cuda.createCannyEdgeDetector(100, 200, 3)
            return detector.detect(gpu).download()
        except Exception:
            _CUDA_UNUSABLE = True
            log.info("meteor: CUDA Canny unavailable, using CPU")
    return cv2.Canny(image, 100, 200, apertureSize=3)


def prepare_gray(
    image_bgr: np.ndarray,
    mask_path: Path | None,
    scale: float,
    use_cuda: bool = False,
) -> np.ndarray:
    gray = _gray_scaled(image_bgr, scale, use_cuda)
    return _apply_mask(gray, mask_path)


def _crop(image: np.ndarray, lines: list[tuple[int, int, int, int]], pad: int = 48) -> np.ndarray:
    h, w = image.shape[:2]
    xs = [c for line in lines for c in (line[0], line[2])]
    ys = [c for line in lines for c in (line[1], line[3])]
    x1 = max(0, min(xs) - pad)
    y1 = max(0, min(ys) - pad)
    x2 = min(w, max(xs) + pad)
    y2 = min(h, max(ys) + pad)
    if x2 <= x1 or y2 <= y1:
        return image
    return image[y1:y2, x1:x2]


def save_hit(
    image_bgr: np.ndarray,
    lines: list[tuple[int, int, int, int]],
    dest_dir: Path,
    when: datetime | None = None,
) -> dict:
    """Write the full frame, a crop around the streak, and a small JSON sidecar."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    when = when or datetime.now().astimezone()
    stamp = when.strftime("%Y%m%d_%H%M%S")
    if (dest_dir / f"meteor_{stamp}.jpg").exists():
        stamp = f"{stamp}_{when.microsecond // 1000:03d}"
    full_name = f"meteor_{stamp}.jpg"
    crop_name = f"meteor_{stamp}_crop.jpg"
    json_name = f"meteor_{stamp}.json"
    cv2.imwrite(str(dest_dir / full_name), image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(dest_dir / crop_name), _crop(image_bgr, lines), [cv2.IMWRITE_JPEG_QUALITY, 92])
    payload = {
        "time": when.isoformat(timespec="seconds"),
        "lines": [{"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)} for x1, y1, x2, y2 in lines],
        "meteor_count": len(lines),
        "frame": full_name,
        "crop": crop_name,
    }
    (dest_dir / json_name).write_text(json.dumps(payload, indent=2))
    return payload


def analyze(
    image_path: Path,
    min_length: int = 100,
    max_length: int = 0,
    annotate: bool = True,
    mask_path: Path | None = None,
    previous_gray: np.ndarray | None = None,
    history: list[np.ndarray] | None = None,
    previous_lines: list[tuple[int, int, int, int]] | None = None,
    scale: float = DEFAULT_SCALE,
    use_cuda: bool = False,
) -> tuple[MeteorResult, np.ndarray | None, np.ndarray | None]:
    """Detect streaks. Returns (result, downscaled gray, full BGR).

    `previous_gray` / `history` are downscaled grayscale frames from earlier
    exposures, not including this one. Without them the temporal filter is
    off (used by the manual "detect now" preview).
    """
    img = cv2.imread(str(image_path))
    if img is None:
        log.warning("meteor: could not read %s", image_path)
        return MeteorResult(), None, None
    original = img.copy()

    full_h, full_w = img.shape[:2]
    small = prepare_gray(img, mask_path, scale, use_cuda=use_cuda)
    ref = _reference(previous_gray, history)
    temporal = ref is not None and ref.shape == small.shape
    if temporal:
        working = cv2.absdiff(small, ref)
        working[working < DIFF_THRESHOLD] = 0
    else:
        working = small

    edges = _canny(working, use_cuda)
    kernel = np.ones((3, 3), np.uint8)
    processed = cv2.dilate(edges, kernel, iterations=2)
    processed = cv2.erode(processed, kernel, iterations=1)

    cloud_mask = np.zeros(processed.shape, np.uint8)
    contours, _ = cv2.findContours(processed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    has_clouds = False
    for cnt in contours:
        if cv2.contourArea(cnt) > 1550 * (scale ** 2):
            has_clouds = True
            cv2.drawContours(cloud_mask, [cnt], 0, 255, -1)
    if has_clouds:
        inv_cloud = cv2.dilate(cv2.bitwise_not(cloud_mask), np.ones((7, 7), np.uint8), iterations=1)
        processed = processed * (inv_cloud // 255)

    lines_raw = cv2.HoughLinesP(
        processed, rho=3, theta=np.pi / 180, threshold=40,
        minLineLength=max(8, int(min_length * scale)), maxLineGap=20,
    )

    diag_small = float(np.hypot(*small.shape[:2]))
    min_small = max(8, int(min_length * scale))
    max_small = (max_length * scale) if max_length > 0 else diag_small * 0.4
    inv = 1.0 / scale if scale else 1.0

    result = MeteorResult(temporal_filter=temporal)
    full_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if lines_raw is not None:
        lines_arr = np.asarray(lines_raw).reshape(-1, 4)
        result.line_count = int(lines_arr.shape[0])
        for x1, y1, x2, y2 in lines_arr:
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            length = _line_length(x1, y1, x2, y2)
            if length < min_small or length > max_small:
                continue
            if temporal and previous_gray is not None and previous_gray.shape == small.shape:
                if _persists_on_previous(previous_gray, x1, y1, x2, y2):
                    continue
            full_line = (
                int(round(x1 * inv)), int(round(y1 * inv)),
                int(round(x2 * inv)), int(round(y2 * inv)),
            )
            if _is_uniform_brightness(full_gray, *full_line):
                continue
            result.candidate_lines.append(full_line)
            if previous_lines and line_continues(full_line, previous_lines, full_w, full_h):
                if annotate:
                    cv2.line(img, (full_line[0], full_line[1]), (full_line[2], full_line[3]), (0, 165, 255), 1)
                continue
            result.meteor_count += 1
            result.lines.append(full_line)
            if annotate:
                cv2.line(img, (full_line[0], full_line[1]), (full_line[2], full_line[3]), (0, 255, 0), 3)

    if annotate and result.meteor_count > 0:
        label = f"Meteors detected: {result.meteor_count}"
        cv2.putText(img, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        result.annotated_jpeg = buf.tobytes()

    return result, small, original


def detect(
    image_path: Path,
    min_length: int = 100,
    max_length: int = 0,
    annotate: bool = True,
    mask_path: Path | None = None,
    previous_gray: np.ndarray | None = None,
    history: list[np.ndarray] | None = None,
    previous_lines: list[tuple[int, int, int, int]] | None = None,
    scale: float = DEFAULT_SCALE,
    use_cuda: bool = False,
) -> MeteorResult:
    """Run meteor detection on a single image file."""
    result, _, _ = analyze(
        image_path,
        min_length=min_length,
        max_length=max_length,
        annotate=annotate,
        mask_path=mask_path,
        previous_gray=previous_gray,
        history=history,
        previous_lines=previous_lines,
        scale=scale,
        use_cuda=use_cuda,
    )
    return result

"""Rain / moisture detection on the allsky dome.

Detects water droplets on the dome by looking for:
  1. Small bright blobs (droplets catch light and create bright spots)
  2. Reduced contrast in the overall image (moisture diffuses light)
  3. High local variance in regions that should be uniform (sky)

The detection runs against tmp/image.jpg and fires alerts through the
notification infrastructure, similar to meteor and focus watchers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

_MAX_DIM = 800  # downsample for speed


@dataclass
class RainResult:
    rain_detected: bool = False
    confidence: float = 0.0  # 0.0 - 1.0
    droplet_count: int = 0
    contrast_score: float = 0.0  # lower = more rain
    blob_density: float = 0.0  # blobs per 1000px²
    message: str = ""


def detect_rain(
    image_path: Path,
    mask_path: Path | None = None,
    droplet_threshold: int = 15,
    contrast_threshold: float = 40.0,
    confidence_threshold: float = 0.4,
) -> RainResult:
    """Analyze an image for rain/moisture on the dome.

    Args:
        image_path: Path to the image file.
        mask_path: Optional mask (white = excluded areas).
        droplet_threshold: Minimum blob count to consider as rain.
        contrast_threshold: Below this contrast score = likely rain.
        confidence_threshold: Combined confidence above this = rain detected.

    Returns:
        RainResult with detection details.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return RainResult(message="could not read image")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Downsample for speed.
    h, w = gray.shape[:2]
    if max(h, w) > _MAX_DIM:
        scale = _MAX_DIM / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Apply mask if provided (white = excluded).
    analysis_mask = None
    if mask_path and mask_path.exists():
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is not None:
            mask = cv2.resize(mask, (gray.shape[1], gray.shape[0]))
            analysis_mask = cv2.bitwise_not(mask)  # invert: white painted = excluded
            gray = cv2.bitwise_and(gray, gray, mask=analysis_mask)

    ah, aw = gray.shape[:2]
    total_pixels = ah * aw
    if analysis_mask is not None:
        total_pixels = max(1, cv2.countNonZero(analysis_mask))

    # --- Method 1: Blob detection (bright droplets) ---
    # Rain drops on the dome appear as small bright circular blobs.
    # Use adaptive threshold to find bright spots.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, -15,
    )

    # Find small contours (droplet-sized blobs).
    contours, _ = cv2.findContours(adaptive, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    droplet_count = 0
    min_area = 4
    max_area = 200  # droplets are small
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            # Check circularity — droplets are roughly circular.
            perimeter = cv2.arcLength(cnt, True)
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity > 0.3:  # roughly circular
                    droplet_count += 1

    blob_density = (droplet_count / total_pixels) * 1000  # per 1000 pixels

    # --- Method 2: Contrast analysis ---
    # Rain on dome reduces contrast significantly.
    # Use standard deviation of intensity as a contrast metric.
    if analysis_mask is not None:
        pixels = gray[analysis_mask > 0]
    else:
        pixels = gray.flatten()

    contrast_score = float(np.std(pixels)) if len(pixels) > 0 else 0.0

    # --- Method 3: Local variance (texture analysis) ---
    # Rain creates many small high-frequency patterns.
    laplacian = cv2.Laplacian(blurred, cv2.CV_64F)
    if analysis_mask is not None:
        lap_pixels = np.abs(laplacian)[analysis_mask > 0]
    else:
        lap_pixels = np.abs(laplacian).flatten()
    high_freq_ratio = float(np.mean(lap_pixels > 10)) if len(lap_pixels) > 0 else 0.0

    # --- Combine signals into confidence score ---
    # Each signal contributes to the overall confidence.
    signals = []

    # Blob signal: more droplets = more confidence.
    blob_signal = min(1.0, droplet_count / max(1, droplet_threshold * 2))
    signals.append(blob_signal * 0.4)

    # Contrast signal: lower contrast = more confidence.
    contrast_signal = max(0, 1.0 - (contrast_score / max(1, contrast_threshold * 2)))
    signals.append(contrast_signal * 0.3)

    # High frequency signal: more small patterns = more confidence.
    freq_signal = min(1.0, high_freq_ratio / 0.3)
    signals.append(freq_signal * 0.3)

    confidence = sum(signals)

    rain_detected = confidence >= confidence_threshold
    reasons = []
    if droplet_count >= droplet_threshold:
        reasons.append(f"{droplet_count} droplet-like blobs")
    if contrast_score < contrast_threshold:
        reasons.append(f"low contrast ({contrast_score:.1f})")
    if high_freq_ratio > 0.15:
        reasons.append(f"high texture ({high_freq_ratio:.2f})")

    message = ", ".join(reasons) if reasons else "clear"

    return RainResult(
        rain_detected=rain_detected,
        confidence=round(confidence, 3),
        droplet_count=droplet_count,
        contrast_score=round(contrast_score, 2),
        blob_density=round(blob_density, 4),
        message=message,
    )

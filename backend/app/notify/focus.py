"""Focus quality assessment (variance-of-Laplacian method).

Computes a single sharpness score for an allsky frame. Higher = sharper.
The user calibrates a baseline when the camera is known to be in focus, then
we alert when the score drops below `baseline * threshold_pct / 100` for N
consecutive checks — the smoothing prevents false alarms from clouds.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Max image dimension for analysis. We downsample first because:
# 1. Faster — Pi 3B RAM is limited.
# 2. The Laplacian variance is resolution-independent enough for blur detection.
_MAX_DIM = 800


def sharpness_score(image_path: Path) -> float | None:
    """Return the variance-of-Laplacian for the given image, or None on error."""
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None

    h, w = img.shape[:2]
    if max(h, w) > _MAX_DIM:
        scale = _MAX_DIM / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    lap = cv2.Laplacian(img, cv2.CV_64F)
    return float(lap.var())


def assess_focus(image_path: Path, baseline: float | None, threshold_pct: float) -> dict:
    """Return a dict with score, baseline, status ('ok'|'soft'|'unknown')."""
    score = sharpness_score(image_path)
    if score is None:
        return {"score": None, "baseline": baseline, "status": "unknown", "threshold": None}

    if baseline is None or baseline <= 0:
        return {"score": score, "baseline": baseline, "status": "unknown", "threshold": None}

    threshold = baseline * (threshold_pct / 100.0)
    status = "ok" if score >= threshold else "soft"
    return {
        "score": round(score, 2),
        "baseline": round(baseline, 2),
        "threshold": round(threshold, 2),
        "status": status,
    }

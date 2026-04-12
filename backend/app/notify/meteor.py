"""Meteor (falling star / streak) detection in allsky images.

Algorithm (same family as upstream's allsky_meteor.py):
  1. Grayscale + Canny edge detection
  2. Dilate edges to connect broken streaks, then erode back
  3. Build a cloud mask via large-area contour removal (clouds have big edges
     but they aren't straight lines)
  4. Probabilistic Hough Line Transform to find line segments
  5. Filter by minimum length
  6. Return detected lines + annotated image

This runs standalone on any JPEG file — it doesn't depend on the upstream
`allsky_shared` module or the `flow-runner` pipeline. We run it periodically
against `tmp/image.jpg` and fire alerts through the notifier infrastructure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class MeteorResult:
    meteor_count: int = 0
    line_count: int = 0
    lines: list[tuple[int, int, int, int]] = field(default_factory=list)
    annotated_jpeg: bytes | None = None


def detect(
    image_path: Path,
    min_length: int = 100,
    annotate: bool = True,
    mask_path: Path | None = None,
) -> MeteorResult:
    """Run meteor detection on a single image file.

    Returns a MeteorResult with counts and optionally an annotated JPEG.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        log.warning("meteor: could not read %s", image_path)
        return MeteorResult()

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Canny edge detection.
    edges = cv2.Canny(gray.astype(np.uint8), 100, 200, apertureSize=3)

    # Dilate to connect broken streaks, then erode to thin back down.
    kernel = np.ones((3, 3), np.uint8)
    processed = cv2.dilate(edges, kernel, iterations=2)
    processed = cv2.erode(processed, kernel, iterations=1)

    # Cloud mask: contours with area > 1550 are likely clouds / bright areas.
    cloud_mask = np.zeros(processed.shape, np.uint8)
    contours, _ = cv2.findContours(processed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    has_clouds = False
    for cnt in contours:
        if cv2.contourArea(cnt) > 1550:
            has_clouds = True
            cv2.drawContours(cloud_mask, [cnt], 0, 255, -1)

    if has_clouds:
        kernel_dilate = np.ones((7, 7), np.uint8)
        inv_cloud = cv2.bitwise_not(cloud_mask)
        inv_cloud = cv2.dilate(inv_cloud, kernel_dilate, iterations=1)
        processed = processed * (inv_cloud // 255)

    # Apply user mask if provided.
    if mask_path and mask_path.exists():
        mask_img = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask_img is not None and mask_img.shape == processed.shape:
            processed = cv2.bitwise_and(processed, processed, mask=mask_img)

    # Hough Line Transform.
    lines_raw = cv2.HoughLinesP(
        processed, rho=3, theta=np.pi / 180, threshold=100,
        minLineLength=min_length, maxLineGap=20,
    )

    result = MeteorResult()
    if lines_raw is not None:
        result.line_count = lines_raw.shape[0]
        for i in range(lines_raw.shape[0]):
            for x1, y1, x2, y2 in lines_raw[i]:
                length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if length >= min_length:
                    result.meteor_count += 1
                    result.lines.append((int(x1), int(y1), int(x2), int(y2)))
                    if annotate:
                        cv2.line(img, (x1, y1), (x2, y2), (0, 255, 0), 3)

    if annotate and result.meteor_count > 0:
        # Add text overlay.
        label = f"Meteors detected: {result.meteor_count}"
        cv2.putText(img, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        result.annotated_jpeg = buf.tobytes()

    return result

"""Full-resolution meteor detection using the detector from the capture tree.

CUDA is used for the grayscale/resize and Canny steps when OpenCV was built
with cv2.cuda and a device is visible. Otherwise the same function runs on
the CPU. Hough stays on the CPU either way.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger("allsky-processor")


def ensure_backend_path() -> None:
    here = Path(__file__).resolve()
    repo = here.parents[2]
    candidates = [
        os.environ.get("ALLSKY_BACKEND", ""),
        "/opt/allsky-web/backend",
        str(repo / "backend"),
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "app" / "notify" / "meteor.py").is_file():
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return


class NightDetector:
    """One-frame-delay confirmation, same idea as the Pi watcher, at full scale."""

    def __init__(self, scale: float = 1.0, min_length: int = 100, use_cuda: bool = False):
        self.scale = scale
        self.min_length = min_length
        self.use_cuda = use_cuda
        self.history: list = []
        self.previous_lines: list = []
        self.pending: dict | None = None
        self.last_when: datetime | None = None

    def reset(self) -> None:
        self.history = []
        self.previous_lines = []
        self.pending = None

    def feed(self, image: Path, when: datetime, dest: Path, mask: Path | None) -> dict | None:
        gap = None
        if self.last_when is not None:
            gap = (when - self.last_when).total_seconds()
        self.last_when = when
        if gap is not None and gap > 30:
            self.reset()
        ensure_backend_path()
        from app.notify.meteor import analyze, line_continues, save_hit

        result, small, original = analyze(
            image,
            min_length=self.min_length,
            max_length=0,
            annotate=True,
            mask_path=mask if mask and mask.is_file() else None,
            previous_gray=self.history[-1] if self.history else None,
            history=list(self.history),
            previous_lines=self.previous_lines,
            scale=self.scale,
            use_cuda=self.use_cuda,
        )
        saved = None
        if self.pending and self.pending.get("lines") and original is not None:
            height, width = self.pending["image"].shape[:2]
            survivors = [
                line for line in self.pending["lines"]
                if not line_continues(line, result.candidate_lines, width, height)
            ]
            if survivors:
                saved = save_hit(self.pending["image"], survivors, dest, self.pending["when"])
                log.info("meteor hit %s", saved.get("frame"))
        if small is not None:
            self.history = (self.history + [small])[-3:]
        self.previous_lines = list(result.candidate_lines)
        if result.candidate_lines and original is not None:
            self.pending = {
                "lines": list(result.candidate_lines),
                "image": original,
                "when": when,
            }
        else:
            self.pending = None
        return saved

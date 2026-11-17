"""Small CLI used by the capture shell scripts.

  mode.py --quiet              exit 0 when capture-only, else 1
  mode.py --apply-quality FILE rewrite the capture args file's quality line
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse

from offload.config import load_config


def apply_quality(args_file: Path, quality: int) -> None:
    lines: list[str] = []
    if args_file.is_file():
        lines = [
            line for line in args_file.read_text().splitlines()
            if not line.startswith("quality=")
        ]
    lines.append(f"quality={int(quality)}")
    args_file.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offload mode helper")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--apply-quality", default="")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.apply_quality:
        if cfg.capture_only:
            apply_quality(Path(args.apply_quality), cfg.jpeg_quality)
        return 0
    if args.quiet:
        return 0 if cfg.capture_only else 1
    print(cfg.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())

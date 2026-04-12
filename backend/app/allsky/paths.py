"""Mirrors the path layout from upstream Allsky's variables.sh.

Keeping this isolated means a future Allsky reorganisation only requires changes
in one place. We deliberately read paths lazily so unit tests can override
ALLSKY_HOME without re-importing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


@dataclass(frozen=True)
class AllskyPaths:
    home: Path

    # --- top level ---
    @property
    def tmp(self) -> Path:
        return self.home / "tmp"

    @property
    def config(self) -> Path:
        return self.home / "config"

    @property
    def scripts(self) -> Path:
        return self.home / "scripts"

    @property
    def bin(self) -> Path:
        return self.home / "bin"

    @property
    def images(self) -> Path:
        return self.home / "images"

    @property
    def darks(self) -> Path:
        return self.home / "darks"

    @property
    def html(self) -> Path:
        return self.home / "html"

    # --- key files ---
    @property
    def latest_image(self) -> Path:
        # The capture loop atomically mv's the finished frame here.
        return self.tmp / "image.jpg"

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    @property
    def options_file(self) -> Path:
        return self.config / "options.json"

    @property
    def status_file(self) -> Path:
        return self.config / "status.json"

    @property
    def messages_file(self) -> Path:
        return self.config / "messages.txt"

    @property
    def env_file(self) -> Path:
        return self.home / "env.json"

    @property
    def connected_cameras(self) -> Path:
        return self.config / "connected_cameras.txt"

    @property
    def make_changes_script(self) -> Path:
        return self.scripts / "makeChanges.sh"

    # --- artefact dirs (per-day) ---
    def day_dir(self, date_name: str) -> Path:
        return self.images / date_name

    def day_thumbnails(self, date_name: str) -> Path:
        return self.day_dir(date_name) / "thumbnails"

    @property
    def keograms_dir(self) -> Path:
        return self.html / "allsky" / "keograms"

    @property
    def startrails_dir(self) -> Path:
        return self.html / "allsky" / "startrails"

    @property
    def videos_dir(self) -> Path:
        return self.html / "allsky" / "videos"

    # --- masks ---
    @property
    def masks_dir(self) -> Path:
        # Same directory the upstream allsky_maskimage.py module reads from.
        return self.config / "overlay" / "images"

    # --- service / logs ---
    @property
    def allsky_log(self) -> Path:
        return Path("/var/log/allsky.log")

    @property
    def version_file(self) -> Path:
        return self.home / "version"


def paths() -> AllskyPaths:
    return AllskyPaths(home=get_settings().allsky_home)

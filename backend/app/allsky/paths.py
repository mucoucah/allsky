"""Mirrors the path layout from upstream Allsky's variables.sh.

Keeping this isolated means a future Allsky reorganisation only requires changes
in one place. We deliberately read paths lazily so unit tests can override
ALLSKY_HOME without re-importing.

Config file resolution:
  The web service user (allskyweb) often cannot read files inside the real
  user's home directory on modern Debian/Bookworm (home dirs are 700).
  To work around this, the installer copies config files to a web-readable
  location (ALLSKY_WEB_CONFIG, typically /opt/allsky-web/config/).
  The ``_cfg`` helper tries the web config copy first, then falls back to
  the original ALLSKY_HOME/config path.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AllskyPaths:
    home: Path
    web_config: Path  # installer-managed readable copy of config

    # --- top level ---
    @property
    def tmp(self) -> Path:
        return self.home / "tmp"

    @property
    def config(self) -> Path:
        """The upstream Allsky config dir (may not be readable by the web user)."""
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

    # --- config file resolution ---
    def _cfg(self, name: str) -> Path:
        """Return the first readable location for a config file.

        Priority:
          1. web_config/<name>  (owned by allskyweb, always readable)
          2. ALLSKY_HOME/config/<name>  (may fail on restricted home dirs)
        """
        web_copy = self.web_config / name
        if web_copy.exists():
            try:
                # Quick readability check.
                web_copy.open("r").close()
                return web_copy
            except OSError:
                pass
        home_copy = self.config / name
        if home_copy.exists():
            try:
                home_copy.open("r").close()
                return home_copy
            except OSError:
                log.warning("config file %s exists but is not readable", home_copy)
        # Return web_config path as canonical even if missing — gives a clear error.
        return web_copy

    # --- key files ---
    @property
    def latest_image(self) -> Path:
        # The capture loop atomically mv's the finished frame here.
        return self.tmp / "image.jpg"

    @property
    def settings_file(self) -> Path:
        return self._cfg("settings.json")

    @property
    def options_file(self) -> Path:
        return self._cfg("options.json")

    @property
    def status_file(self) -> Path:
        return self._cfg("status.json")

    @property
    def settings_file_allsky_home(self) -> Path:
        """Always returns the ALLSKY_HOME copy (for writing back to upstream)."""
        return self.config / "settings.json"

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
    s = get_settings()
    return AllskyPaths(home=s.allsky_home, web_config=s.web_config_dir)

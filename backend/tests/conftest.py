"""Keep tests off the real Allsky home and data directories."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("ALLSKY_HOME", tempfile.mkdtemp(prefix="allsky-home-"))
os.environ.setdefault("ALLSKY_WEB_CONFIG", tempfile.mkdtemp(prefix="allsky-webcfg-"))
os.environ.setdefault("ALLSKY_WEB_DATA", tempfile.mkdtemp(prefix="allsky-data-"))
os.environ.setdefault("ALLSKY_WEB_AUTH", "0")
os.environ.setdefault("ALLSKY_WEB_PASS_HASH", "")

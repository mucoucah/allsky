"""One configuration file for capture-only mode and the PC processor.

Search order:
  1. ALLSKY_OFFLOAD_CONFIG
  2. ALLSKY_HOME/config/offload.json
  3. /etc/allsky/offload.json

A missing file means mode "normal": the Pi keeps doing its own processing.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_OUTBOX_MAX_BYTES = 4 * 1024 * 1024 * 1024


@dataclass
class RemoteConfig:
    host: str = ""
    port: int = 2222
    user: str = ""
    path: str = "/srv/allsky/incoming"
    ssh_key: str = ""
    bandwidth_limit_kbps: int = 0
    settings_path: str = "/srv/allsky/to-pi"
    status_name: str = "status/pi-status.json"


@dataclass
class ProcessorConfig:
    incoming_dir: str = "/srv/allsky/incoming"
    data_dir: str = "/srv/allsky/data"
    to_pi_dir: str = "/srv/allsky/to-pi"
    retention_days: int = 14
    # Age of raw frames kept under images/<YYYYMMDD>/. Products are not deleted.
    # When this key is absent, retention_days is used so older configs keep
    # the same raw-frame window. 0 disables age-based raw deletion.
    raw_retention_days: int = 14
    min_free_gb: float = 10.0
    max_disk_bytes: int = 0
    encoder: str = "auto"
    meteor_scale: float = 1.0
    use_cuda: str = "auto"
    min_streak_length: int = 100
    poll_seconds: float = 2.0
    quiet_with_day_seconds: int = 300
    quiet_alone_seconds: int = 45 * 60


@dataclass
class OffloadConfig:
    mode: str = "normal"
    jpeg_quality: int = 90
    outbox_dir: str = "/var/lib/allsky/outbox"
    outbox_max_bytes: int = DEFAULT_OUTBOX_MAX_BYTES
    drop_day_frames: bool = False
    night_priority: bool = True
    remote: RemoteConfig = field(default_factory=RemoteConfig)
    processor: ProcessorConfig = field(default_factory=ProcessorConfig)

    @property
    def capture_only(self) -> bool:
        return self.mode == "capture-only"


# Fields the PC may push back to the Pi. SSH target stays on the Pi.
PUSH_FIELDS = (
    "mode",
    "jpeg_quality",
    "drop_day_frames",
    "night_priority",
    "outbox_max_bytes",
    "bandwidth_limit_kbps",
)


def config_path() -> Path | None:
    explicit = os.environ.get("ALLSKY_OFFLOAD_CONFIG", "").strip()
    if explicit:
        return Path(explicit)
    home = os.environ.get("ALLSKY_HOME", "").strip()
    if home:
        candidate = Path(home) / "config" / "offload.json"
        etc = Path("/etc/allsky/offload.json")
        if candidate.is_file() or not etc.is_file():
            return candidate
        return etc
    etc = Path("/etc/allsky/offload.json")
    if etc.is_file():
        return etc
    return None


def _remote_from(data: dict[str, Any] | None) -> RemoteConfig:
    raw = data or {}
    base = RemoteConfig()
    for key in asdict(base):
        if key in raw and raw[key] is not None:
            setattr(base, key, raw[key])
    base.port = int(base.port)
    base.bandwidth_limit_kbps = int(base.bandwidth_limit_kbps)
    return base


def _processor_from(data: dict[str, Any] | None) -> ProcessorConfig:
    raw = data or {}
    base = ProcessorConfig()
    for key in asdict(base):
        if key in raw and raw[key] is not None:
            setattr(base, key, raw[key])
    base.retention_days = int(base.retention_days)
    base.max_disk_bytes = int(base.max_disk_bytes)
    if "raw_retention_days" not in raw and "retention_days" in raw:
        base.raw_retention_days = int(raw["retention_days"])
    base.raw_retention_days = int(base.raw_retention_days)
    base.min_free_gb = float(base.min_free_gb)
    base.meteor_scale = float(base.meteor_scale)
    base.min_streak_length = int(base.min_streak_length)
    base.poll_seconds = float(base.poll_seconds)
    base.quiet_with_day_seconds = int(base.quiet_with_day_seconds)
    base.quiet_alone_seconds = int(base.quiet_alone_seconds)
    return base


def from_dict(data: dict[str, Any] | None) -> OffloadConfig:
    raw = data or {}
    cfg = OffloadConfig()
    if raw.get("mode"):
        cfg.mode = str(raw["mode"]).strip()
    if raw.get("jpeg_quality") is not None:
        cfg.jpeg_quality = int(raw["jpeg_quality"])
    if raw.get("outbox_dir"):
        cfg.outbox_dir = str(raw["outbox_dir"])
    if raw.get("outbox_max_bytes") is not None:
        cfg.outbox_max_bytes = int(raw["outbox_max_bytes"])
    cfg.drop_day_frames = bool(raw.get("drop_day_frames", False))
    cfg.night_priority = bool(raw.get("night_priority", True))
    cfg.remote = _remote_from(raw.get("remote") if isinstance(raw.get("remote"), dict) else {})
    cfg.processor = _processor_from(
        raw.get("processor") if isinstance(raw.get("processor"), dict) else {}
    )
    return cfg


def load_config(path: Path | None = None) -> OffloadConfig:
    file = path if path is not None else config_path()
    if file is None or not file.is_file():
        return OffloadConfig()
    try:
        data = json.loads(file.read_text())
    except (OSError, json.JSONDecodeError):
        return OffloadConfig()
    if not isinstance(data, dict):
        return OffloadConfig()
    return from_dict(data)


def to_dict(cfg: OffloadConfig) -> dict[str, Any]:
    return asdict(cfg)


def validate_config(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        cfg = from_dict(data)
    except (TypeError, ValueError) as exc:
        return [f"invalid offload config: {exc}"]
    if cfg.mode not in ("normal", "capture-only"):
        errors.append("mode must be normal or capture-only")
    if not 1 <= cfg.jpeg_quality <= 100:
        errors.append("jpeg_quality must be between 1 and 100")
    if cfg.outbox_max_bytes < 0:
        errors.append("outbox_max_bytes must be >= 0")
    remote = cfg.remote
    if not 1 <= remote.port <= 65535:
        errors.append("remote.port must be between 1 and 65535")
    if remote.bandwidth_limit_kbps < 0:
        errors.append("remote.bandwidth_limit_kbps must be >= 0")
    proc = cfg.processor
    if proc.retention_days < 1:
        errors.append("processor.retention_days must be >= 1")
    if proc.raw_retention_days < 0:
        errors.append("processor.raw_retention_days must be >= 0")
    if proc.min_free_gb < 0:
        errors.append("processor.min_free_gb must be >= 0")
    if proc.max_disk_bytes < 0:
        errors.append("processor.max_disk_bytes must be >= 0")
    if proc.meteor_scale <= 0:
        errors.append("processor.meteor_scale must be > 0")
    if proc.encoder not in ("auto", "h264_nvenc", "hevc_nvenc", "libx264"):
        errors.append("processor.encoder must be auto, h264_nvenc, hevc_nvenc, or libx264")
    if proc.use_cuda not in ("auto", "on", "off"):
        errors.append("processor.use_cuda must be auto, on, or off")
    if not 30 <= proc.quiet_with_day_seconds <= 24 * 3600:
        errors.append("processor.quiet_with_day_seconds is out of range")
    if not 60 <= proc.quiet_alone_seconds <= 24 * 3600:
        errors.append("processor.quiet_alone_seconds is out of range")
    return errors


def save_config(cfg: OffloadConfig, path: Path | None = None) -> Path:
    file = path if path is not None else config_path()
    if file is None:
        raise OSError("no offload config path; set ALLSKY_HOME or ALLSKY_OFFLOAD_CONFIG")
    errors = validate_config(to_dict(cfg))
    if errors:
        raise ValueError("; ".join(errors))
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_dict(cfg), indent=2) + "\n"
    tmp = file.with_suffix(file.suffix + ".tmp")
    tmp.write_text(payload)
    os.replace(tmp, file)
    return file


def push_document(cfg: OffloadConfig) -> dict[str, Any]:
    """Subset the Pi sync agent is willing to accept from the PC."""
    return {
        "mode": cfg.mode,
        "jpeg_quality": cfg.jpeg_quality,
        "drop_day_frames": cfg.drop_day_frames,
        "night_priority": cfg.night_priority,
        "outbox_max_bytes": cfg.outbox_max_bytes,
        "bandwidth_limit_kbps": cfg.remote.bandwidth_limit_kbps,
    }


def merge_push(cfg: OffloadConfig, pushed: dict[str, Any]) -> tuple[OffloadConfig, bool]:
    """Apply a PC push. SSH host, user, key, and paths are left alone."""
    changed = False
    allowed = {key: pushed[key] for key in PUSH_FIELDS if key in pushed}
    if "mode" in allowed and str(allowed["mode"]) in ("normal", "capture-only"):
        mode = str(allowed["mode"])
        if mode != cfg.mode:
            cfg.mode = mode
            changed = True
    if "jpeg_quality" in allowed:
        quality = int(allowed["jpeg_quality"])
        if quality != cfg.jpeg_quality and 1 <= quality <= 100:
            cfg.jpeg_quality = quality
            changed = True
    if "drop_day_frames" in allowed:
        flag = bool(allowed["drop_day_frames"])
        if flag != cfg.drop_day_frames:
            cfg.drop_day_frames = flag
            changed = True
    if "night_priority" in allowed:
        flag = bool(allowed["night_priority"])
        if flag != cfg.night_priority:
            cfg.night_priority = flag
            changed = True
    if "outbox_max_bytes" in allowed:
        limit = int(allowed["outbox_max_bytes"])
        if limit >= 0 and limit != cfg.outbox_max_bytes:
            cfg.outbox_max_bytes = limit
            changed = True
    if "bandwidth_limit_kbps" in allowed:
        limit = int(allowed["bandwidth_limit_kbps"])
        if limit >= 0 and limit != cfg.remote.bandwidth_limit_kbps:
            cfg.remote.bandwidth_limit_kbps = limit
            changed = True
    return cfg, changed


def capture_only_enabled(path: Path | None = None) -> bool:
    return load_config(path).capture_only

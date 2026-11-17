"""Offload mode: Pi capture-only settings and the camera's heartbeat."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/offload", tags=["offload"])


def _ensure_offload_path() -> None:
    here = Path(__file__).resolve()
    candidates = []
    home = __import__("os").environ.get("ALLSKY_HOME", "")
    if home:
        candidates.append(Path(home))
    # backend/app/routers/offload.py -> repo root is parents[3]
    candidates.append(here.parents[3])
    candidates.append(Path("/opt/allsky-processor"))
    for root in candidates:
        if (root / "offload" / "config.py").is_file():
            text = str(root)
            if text not in sys.path:
                sys.path.insert(0, text)
            return


def _load():
    _ensure_offload_path()
    from offload.config import config_path, load_config, to_dict
    cfg = load_config()
    path = config_path()
    payload = to_dict(cfg)
    payload["persisted"] = bool(path and path.is_file())
    payload["path"] = str(path) if path else None
    return cfg, payload


def _status_file(cfg) -> Path | None:
    import os
    explicit = os.environ.get("ALLSKY_PI_STATUS", "").strip()
    if explicit:
        return Path(explicit)
    incoming = Path(cfg.processor.incoming_dir)
    candidate = incoming / "status" / "pi-status.json"
    if candidate.is_file():
        return candidate
    data = Path(cfg.processor.data_dir) / "tmp" / "pi-status.json"
    if data.is_file():
        return data
    home = os.environ.get("ALLSKY_HOME", "")
    if home:
        local = Path(home) / "tmp" / "pi-status.json"
        if local.is_file():
            return local
    return candidate


def publish_for_pi(cfg) -> None:
    """Write the settings the Pi pulls, next to the processor's to-pi directory."""
    _ensure_offload_path()
    from offload.config import push_document
    dest_dir = Path(cfg.processor.to_pi_dir)
    if not cfg.processor.to_pi_dir:
        return
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        push = dest_dir / "offload-push.json"
        tmp = push.with_suffix(".tmp")
        tmp.write_text(json.dumps(push_document(cfg), indent=2) + "\n")
        tmp.replace(push)
    except OSError as exc:
        log.warning("offload push file not written: %s", exc)


@router.get("")
async def get_offload():
    _cfg, payload = _load()
    return payload


@router.put("")
async def put_offload(body: dict = Body(...)):
    _ensure_offload_path()
    from offload.config import from_dict, save_config, to_dict, validate_config
    errors = validate_config(body)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    cfg = from_dict(body)
    try:
        path = save_config(cfg)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    publish_for_pi(cfg)
    payload = to_dict(cfg)
    payload["persisted"] = True
    payload["path"] = str(path)
    return payload


@router.get("/pi")
async def pi_status():
    cfg, _payload = _load()
    path = _status_file(cfg)
    if path is None or not path.is_file():
        return {
            "ok": False,
            "status": None,
            "message": "No heartbeat yet. The Pi uploads one when the PC is reachable.",
        }
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"heartbeat unreadable: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="heartbeat is not a JSON object")
    return {"ok": True, "status": data, "path": str(path)}

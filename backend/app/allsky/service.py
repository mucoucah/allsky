"""Service control + settings application.

We delegate setting writes to upstream's makeChanges.sh so we inherit its
camera-link / restart logic. systemd control is gated by a sudoers drop-in that
allows ONLY the three allsky.service verbs we need.
"""
from __future__ import annotations

import asyncio
import shlex
from typing import Any

from .paths import paths


class ServiceError(RuntimeError):
    pass


async def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise ServiceError(f"command timed out: {' '.join(shlex.quote(c) for c in cmd)}")
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


# --- systemctl ---

ALLOWED_VERBS = {"start", "stop", "restart", "status"}


async def systemctl(verb: str) -> dict[str, Any]:
    if verb not in ALLOWED_VERBS:
        raise ServiceError(f"verb {verb!r} not allowed")
    cmd = ["sudo", "-n", "systemctl", verb, "allsky.service"]
    if verb == "status":
        # Status doesn't need sudo and we want it to never block on a tty.
        cmd = ["systemctl", "--no-pager", "status", "allsky.service"]
    code, out, err = await _run(cmd)
    return {"verb": verb, "exit_code": code, "stdout": out, "stderr": err}


# --- settings application ---

async def apply_settings(changes: dict[str, Any]) -> dict[str, Any]:
    """Apply a dict of changes by writing directly to settings.json.

    Merges the incoming changes into the current settings, then writes to both
    the web config copy and the allsky home copy so the camera daemon picks them up.

    If upstream's makeChanges.sh exists, we also try to run it for any side-effects
    (camera re-linking, etc.), but a failure there is non-fatal — the settings are
    already persisted.
    """
    import logging
    log = logging.getLogger(__name__)

    from .settings import load_values, save_values

    # Merge changes into current settings.
    current = load_values()
    current.update(changes)
    save_values(current)

    # Best-effort: run makeChanges.sh for side-effects if it exists.
    script = paths().make_changes_script
    script_results: list[dict[str, Any]] = []
    if script.exists():
        for key, value in changes.items():
            if isinstance(value, bool):
                v = "true" if value else "false"
            else:
                v = str(value)
            try:
                cmd = ["bash", str(script), key, key, "", v]
                code, out, err = await _run(cmd, timeout=60.0)
                script_results.append(
                    {"key": key, "value": v, "exit_code": code, "stdout": out, "stderr": err}
                )
            except Exception as e:
                log.warning("makeChanges.sh failed for %s: %s (non-fatal)", key, e)
                script_results.append({"key": key, "value": v, "exit_code": -1, "error": str(e)})

    return {"ok": True, "saved": list(changes.keys()), "script_results": script_results}

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
    """Apply a dict of changes via upstream makeChanges.sh.

    Each call form is:
        makeChanges.sh <key> <label> <oldvalue> <newvalue>

    We don't know the human label or old value reliably, so we pass placeholders
    that mirror what the upstream WebUI does. makeChanges.sh handles re-linking
    camera-specific files and triggering the appropriate restarts.
    """
    script = paths().make_changes_script
    if not script.exists():
        raise ServiceError(f"makeChanges.sh not found at {script}")

    results: list[dict[str, Any]] = []
    for key, value in changes.items():
        # makeChanges.sh expects strings; booleans become "true"/"false".
        if isinstance(value, bool):
            v = "true" if value else "false"
        else:
            v = str(value)
        # placeholder old value "" — script handles missing-old-value gracefully.
        cmd = ["bash", str(script), key, key, "", v]
        code, out, err = await _run(cmd, timeout=60.0)
        results.append(
            {"key": key, "value": v, "exit_code": code, "stdout": out, "stderr": err}
        )
        if code != 0:
            # Stop on first failure so the user sees the offending change.
            return {"ok": False, "results": results}
    return {"ok": True, "results": results}

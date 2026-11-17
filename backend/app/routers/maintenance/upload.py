"""Website upload test. URL stays /api/maintenance/upload/test."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Body, HTTPException

from app.allsky.paths import paths
from app.allsky.settings import load_values, save_values

router = APIRouter()

async def test_upload(body: dict = Body(...)):
    """Test upload configuration by uploading a small test file."""
    upload_type = body.get("type", "remote-web")  # local-web, remote-web, remote-server

    # Save the upload settings first.
    values = load_values()
    for k, v in body.items():
        if k == "type":
            continue
        # Prefix upload-related keys to match settings schema.
        values[k] = v
    save_values(values)

    # Create a test file.
    tmp = paths().tmp
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    test_file = tmp / "upload_test.txt"
    test_file.write_text(f"Allsky upload test\n")

    # Run testUpload.sh
    script = paths().scripts / "testUpload.sh"
    if not script.exists():
        raise HTTPException(500, f"testUpload.sh not found at {script}")

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(script), f"--{upload_type}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ALLSKY_HOME": str(paths().home)},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = (stdout + stderr).decode(errors="replace")
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": output[-4000:],  # tail in case of huge output
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Upload test timed out after 60s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

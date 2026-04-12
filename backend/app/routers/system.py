"""System status + Allsky service control."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.allsky.service import ServiceError, systemctl
from app.allsky.status import read_camera_info, read_messages, read_status, read_version
from app.allsky.system import system_snapshot

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("")
async def system_status():
    return {
        "host": system_snapshot(),
        "allsky": {
            "version": read_version(),
            **read_status(),
            "camera": read_camera_info(),
        },
    }


@router.get("/messages")
async def messages(limit: int = 50):
    return read_messages(limit=limit)


@router.post("/service/{verb}")
async def service_control(verb: str):
    try:
        return await systemctl(verb)
    except ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))

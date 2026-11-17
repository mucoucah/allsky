"""Maintenance routes, split by section. The public URLs are unchanged."""
from fastapi import APIRouter

from . import darks, dailylapse, generate, overlay, updates, upload

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
for _part in (updates, darks, upload, generate, overlay, dailylapse):
    router.include_router(_part.router)

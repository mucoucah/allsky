"""Notification routes, split by section. The public URLs are unchanged."""
from fastapi import APIRouter

from . import adsb, channels, focus, meteor, rain, satellites

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
for _part in (channels, meteor, focus, rain, adsb, satellites):
    router.include_router(_part.router)

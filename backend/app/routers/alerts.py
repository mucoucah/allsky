"""Alerts CRUD backed by SQLite."""
from __future__ import annotations

import time

from fastapi import APIRouter, Body, HTTPException

from app.db import connect, insert_alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(unacknowledged_only: bool = False, limit: int = 100):
    sql = "SELECT * FROM alerts"
    args: tuple = ()
    if unacknowledged_only:
        sql += " WHERE acknowledged_at IS NULL"
    sql += " ORDER BY created_at DESC LIMIT ?"
    args = args + (limit,)
    async with connect() as conn:
        cur = await conn.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]


@router.post("")
async def create_alert(body: dict = Body(...)):
    level = body.get("level", "info")
    source = body.get("source", "user")
    message = body.get("message", "")
    if not message:
        raise HTTPException(400, "message required")
    aid = await insert_alert(level, source, message)
    return {"id": aid}


@router.post("/{alert_id}/ack")
async def ack(alert_id: int):
    async with connect() as conn:
        await conn.execute(
            "UPDATE alerts SET acknowledged_at=? WHERE id=?", (time.time(), alert_id)
        )
        await conn.commit()
    return {"ok": True}

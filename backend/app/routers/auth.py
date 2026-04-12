"""Optional session-cookie auth.

If ALLSKY_WEB_USER is empty in env, auth is fully disabled (LAN-trusted mode).
Otherwise we require a single shared user/bcrypt-hash, set via env vars.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def auth_required() -> bool:
    s = get_settings()
    return bool(s.auth_user)


def _verify(password: str) -> bool:
    s = get_settings()
    if not s.auth_pass_hash:
        return False
    try:
        from passlib.hash import bcrypt
    except ImportError:
        return False
    try:
        return bcrypt.verify(password, s.auth_pass_hash)
    except (ValueError, TypeError):
        return False


@router.get("/whoami")
async def whoami(req: Request):
    if not auth_required():
        return {"authenticated": True, "user": "anonymous", "auth_disabled": True}
    user = req.session.get("user")
    return {"authenticated": bool(user), "user": user}


@router.post("/login")
async def login(req: Request, body: dict = Body(...)):
    if not auth_required():
        return {"ok": True, "auth_disabled": True}
    s = get_settings()
    user = body.get("user", "")
    password = body.get("password", "")
    if user != s.auth_user or not _verify(password):
        raise HTTPException(401, "invalid credentials")
    req.session["user"] = user
    return {"ok": True, "user": user}


@router.post("/logout")
async def logout(req: Request):
    req.session.clear()
    return {"ok": True}

"""FastAPI app entrypoint.

Layout:
  /api/...      JSON + WS endpoints
  /            (in production) the built React bundle is served by lighttpd in
               front of us; during development the Vite dev-server runs on
               :5173 and proxies /api back here.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.allsky.watcher import watch_latest_image
from app.config import get_settings
from app.db import init_db
from app.notify.watchers import focus_watcher, meteor_watcher
from app.routers import alerts, auth, images, keograms, live, masks, notifications, settings, system
from app.ws.manager import LiveBroadcaster

log = logging.getLogger("allskyweb")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    log.info("starting allsky-web (allsky_home=%s)", s.allsky_home)
    await init_db()

    app.state.broadcaster = LiveBroadcaster()
    app.state.watcher_stop = asyncio.Event()
    app.state.watcher_task = asyncio.create_task(
        watch_latest_image(app.state.broadcaster, app.state.watcher_stop)
    )
    # Alert watchers (meteor detection + focus monitoring).
    app.state.meteor_task = asyncio.create_task(meteor_watcher(app.state.watcher_stop))
    app.state.focus_task = asyncio.create_task(focus_watcher(app.state.watcher_stop))

    try:
        yield
    finally:
        app.state.watcher_stop.set()
        for task in (
            app.state.watcher_task,
            app.state.meteor_task,
            app.state.focus_task,
        ):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        log.info("shutdown complete")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="allsky-web", version="0.1.0", lifespan=lifespan)

    app.add_middleware(SessionMiddleware, secret_key=s.session_secret, https_only=False)
    if s.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    for r in (
        live.router,
        system.router,
        settings.router,
        images.router,
        masks.router,
        keograms.router,
        alerts.router,
        auth.router,
        notifications.router,
    ):
        app.include_router(r)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": "0.1.0"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)

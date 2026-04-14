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
from app.notify.watchers import focus_watcher, meteor_watcher, rain_watcher
from app.routers import alerts, auth, images, keograms, live, logs, maintenance, masks, notifications, settings, setup, system
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
    # Alert watchers (meteor detection + focus monitoring + rain detection).
    app.state.meteor_task = asyncio.create_task(meteor_watcher(app.state.watcher_stop))
    app.state.focus_task = asyncio.create_task(focus_watcher(app.state.watcher_stop))
    app.state.rain_task = asyncio.create_task(rain_watcher(app.state.watcher_stop))

    try:
        yield
    finally:
        app.state.watcher_stop.set()
        for task in (
            app.state.watcher_task,
            app.state.meteor_task,
            app.state.focus_task,
            app.state.rain_task,
        ):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        log.info("shutdown complete")


def create_app() -> FastAPI:
    s = get_settings()
    from app import __version__
    app = FastAPI(title="allsky-web", version=__version__, lifespan=lifespan)

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
        logs.router,
        setup.router,
        maintenance.router,
    ):
        app.include_router(r)

    @app.get("/api/health")
    async def health():
        from app import __version__
        return {"ok": True, "version": __version__}

    # Serve the built React frontend when running standalone (no lighttpd).
    # Must come AFTER API routes so /api/* takes priority.
    _mount_frontend(app)

    return app


def _mount_frontend(app: FastAPI) -> None:
    """Mount the React SPA if the dist directory exists.

    This makes lighttpd optional — FastAPI serves the built frontend directly.
    Must be called AFTER all /api/* routes so they take priority.
    """
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    # Check two locations: sibling frontend/dist (dev) and /opt/allsky-web/frontend/dist (prod).
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        Path("/opt/allsky-web/frontend/dist"),
    ]
    dist = next((c for c in candidates if c.is_dir()), None)
    if not dist:
        log.info("frontend dist not found — API-only mode")
        return

    index_html = dist / "index.html"
    if not index_html.exists():
        log.warning("frontend dist exists but no index.html — skipping SPA mount")
        return

    log.info("serving frontend from %s", dist)

    # Serve the entire dist tree as static files, with SPA fallback.
    # The catch-all must come last so /api/* routes win.
    @app.get("/{path:path}", include_in_schema=False)
    async def spa_or_static(path: str):
        # Try to serve a real file first.
        candidate = dist / path
        if candidate.is_file() and ".." not in path:
            return FileResponse(str(candidate))
        # Everything else → index.html (SPA client-side routing).
        return FileResponse(str(index_html))


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)

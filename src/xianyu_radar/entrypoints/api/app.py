"""FastAPI application for xianyu-radar web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from xianyu_radar import __version__
from xianyu_radar.entrypoints.api.routes import (
    auth,
    candidates,
    discover,
    events,
    pool,
    scan,
    status,
)
from xianyu_radar.config import ROOT_DIR, ensure_data_dirs
from xianyu_radar.infrastructure.storage.db import init_db

WEB_DIR = ROOT_DIR / "web"


class SameOriginWriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin and origin.rstrip("/") != f"{scope['scheme']}://{headers.get('host', '')}":
                response = JSONResponse(status_code=403, content={"detail": "跨站请求已拒绝"})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    ensure_data_dirs()
    init_db().close()

    app = FastAPI(
        title="xianyu-radar",
        version=__version__,
        description="Merchant monitoring & candidate discovery API",
    )
    app.add_middleware(SameOriginWriteMiddleware)

    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(discover.router, prefix="/api/discover", tags=["discover"])
    app.include_router(pool.router, prefix="/api/pool", tags=["pool"])
    app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
    app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])

    if WEB_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()

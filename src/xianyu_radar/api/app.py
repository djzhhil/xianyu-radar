"""FastAPI application for xianyu-radar web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from xianyu_radar import __version__
from xianyu_radar.api.routes import (
    auth,
    candidates,
    demo,
    discover,
    env,
    events,
    pool,
    scan,
    status,
)
from xianyu_radar.config import ROOT_DIR, apply_env, ensure_data_dirs
from xianyu_radar.storage.db import init_db

WEB_DIR = ROOT_DIR / "web"


def create_app(radar_env: str | None = None) -> FastAPI:
    apply_env(radar_env)
    ensure_data_dirs()
    init_db().close()

    app = FastAPI(
        title="xianyu-radar",
        version=__version__,
        description="Merchant monitoring & candidate discovery API",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(env.router, prefix="/api/env", tags=["env"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(discover.router, prefix="/api/discover", tags=["discover"])
    app.include_router(pool.router, prefix="/api/pool", tags=["pool"])
    app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
    app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])
    app.include_router(demo.router, prefix="/api/demo", tags=["demo"])

    if WEB_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()

"""Auth endpoints."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xianyu_radar.entrypoints.api.deps import get_db, require_session
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.modules.auth import service

router = APIRouter()


class SessionBody(BaseModel):
    """Accept either full Asher snapshot or {cookie/cookies}."""

    payload: dict[str, Any] = Field(..., description="Session JSON object")
    filename: str = "default.json"


@router.get("/status")
def auth_status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return service.session_status(conn)


@router.post("/session")
def save_session(body: SessionBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return service.save_session(conn, body.payload, body.filename)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/clear-pause")
def clear_pause(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return service.clear_pause(conn)


@router.post("/check")
def check(ping: bool = False, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return service.check_session(conn, require_session(), ping=ping)

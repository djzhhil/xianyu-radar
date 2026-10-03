"""Helper authentication status and migration endpoints."""
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from xianyu_radar.entrypoints.api.deps import get_db, require_session
from xianyu_radar.modules.auth import service

router = APIRouter()

@router.get("/status")
def auth_status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return service.session_status(conn)

@router.post("/session")
def save_session() -> dict:
    raise HTTPException(status_code=410, detail={"code": "cookie_management_moved_to_helper",
                                               "message": "Cookie 管理已迁移到 Helper；请在 Helper 登录。"})

@router.post("/clear-pause")
def clear_pause(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    with require_session(conn) as session:
        return service.check_session(conn, session, ping=True)

@router.post("/check")
def check(ping: bool = True, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    with require_session(conn) as session:
        return service.check_session(conn, session, ping=ping)

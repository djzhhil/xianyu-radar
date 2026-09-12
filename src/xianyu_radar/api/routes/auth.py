"""Auth endpoints."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xianyu_radar import config as cfg
from xianyu_radar.api.deps import get_db, require_session
from xianyu_radar.auth.session import AuthError, auth_mode, load_session, load_session_local
from xianyu_radar.config import ensure_data_dirs
from xianyu_radar.scheduler.runner import clear_auth_paused, is_auth_paused
from xianyu_radar.security import write_secret_file

router = APIRouter()


class SessionBody(BaseModel):
    """Accept either full Asher snapshot or {cookie/cookies}."""

    payload: dict[str, Any] = Field(..., description="Session JSON object")
    filename: str = "default.json"


def _session_view(session, *, paused: bool) -> dict:
    return {
        "ok": True,
        "source": session.source,
        "cookie_count": session.cookie_count,
        "token_prefix": session.token[:8] + "...",
        "paused": paused,
        "looks_like_placeholder": session.looks_like_placeholder,
        "env": cfg.RADAR_ENV,
        "mode": auth_mode(),
        "from_broker": session.from_broker,
        "account_id": session.account_id or None,
        # lease_id is a short-lived handle; never return cookie material
        "lease_active": bool(session.lease_id),
        "hint": (
            "当前 Cookie 像测试占位符，真实扫描会失败。请粘贴 goofish 登录态。"
            if session.looks_like_placeholder
            else None
        ),
    }


@router.get("/status")
def auth_status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        session = load_session()
        return _session_view(session, paused=is_auth_paused(conn))
    except AuthError as e:
        return {
            "ok": False,
            "error": str(e),
            "paused": is_auth_paused(conn),
            "env": cfg.RADAR_ENV,
            "mode": auth_mode(),
        }


@router.post("/session")
def save_session(body: SessionBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Local cookie paste fallback (ignored as authority when RADAR_AUTH_MODE=broker)."""
    ensure_data_dirs()
    name = Path(body.filename).name
    if not name.endswith(".json"):
        name += ".json"
    path = cfg.STATE_DIR / name
    write_secret_file(
        path,
        json.dumps(body.payload, ensure_ascii=False, indent=2) + "\n",
        mode=0o600,
    )
    try:
        session = load_session_local(path)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    clear_auth_paused(conn)
    out = _session_view(session, paused=False)
    out["path"] = str(path)
    out["path_mode"] = "0600"
    out["note"] = (
        "已写入本地文件（权限 0600）。当前为 broker 模式时，扫描仍优先使用 Helper 租约。"
        if auth_mode() == "broker"
        else "已写入本地文件（权限 0600）。"
    )
    return out


@router.post("/broker/refresh")
def broker_refresh(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Force re-lease from Helper Session Broker."""
    if auth_mode() != "broker":
        raise HTTPException(status_code=400, detail="not in broker mode")
    from xianyu_radar.auth.broker_client import BrokerError, get_broker_client

    try:
        get_broker_client().lease(force=True)
        session = load_session()
    except (BrokerError, AuthError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    clear_auth_paused(conn)
    return _session_view(session, paused=False)


@router.get("/broker/health")
def broker_health() -> dict:
    if auth_mode() != "broker":
        return {"ok": False, "mode": auth_mode(), "error": "not in broker mode"}
    from xianyu_radar.auth.broker_client import BrokerError, get_broker_client

    try:
        return {"ok": True, "mode": "broker", "health": get_broker_client().health()}
    except BrokerError as e:
        return {"ok": False, "mode": "broker", "error": str(e)}


@router.post("/clear-pause")
def clear_pause(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    clear_auth_paused(conn)
    return {"ok": True, "paused": False, "env": cfg.RADAR_ENV}


@router.post("/check")
def check(ping: bool = False, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    session = require_session()
    result = _session_view(session, paused=is_auth_paused(conn))
    if ping:
        if session.looks_like_placeholder:
            result["ping"] = "skip"
            result["ping_error"] = "placeholder cookie; refuse live ping"
            return result
        from xianyu_radar.auth.mtop import call_mtop

        try:
            call_mtop(
                session,
                "taobao.idlemtopsearch.pc.search",
                {
                    "pageNumber": 1,
                    "keyword": "test",
                    "fromFilter": False,
                    "rowsPerPage": 1,
                    "sortValue": "",
                    "sortField": "",
                    "customDistance": "",
                    "gps": "",
                    "propValueStr": {},
                    "customGps": "",
                    "searchReqFromPage": "pcSearch",
                    "extraFilterValue": "{}",
                    "userPositionJson": "{}",
                },
                {"spm_cnt": "a21ybx.search.0.0"},
            )
            result["ping"] = "ok"
            clear_auth_paused(conn)
            result["paused"] = False
        except Exception as e:
            result["ping"] = "fail"
            result["ping_error"] = str(e)
    return result

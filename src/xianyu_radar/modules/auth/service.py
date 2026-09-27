"""Public authentication feature operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from xianyu_radar import config as cfg
from xianyu_radar.config import ensure_data_dirs
from xianyu_radar.infrastructure.goofish.mtop import call_mtop
from xianyu_radar.infrastructure.goofish.session import AuthError, Session, load_session
from xianyu_radar.infrastructure.storage.auth_state import clear_auth_paused, is_auth_paused


def _session_view(session: Session, *, paused: bool) -> dict:
    return {
        "ok": True,
        "source": session.source,
        "cookie_count": session.cookie_count,
        "token_prefix": session.token[:8] + "...",
        "paused": paused,
        "looks_like_placeholder": session.looks_like_placeholder,
        "hint": (
            "当前 Cookie 像测试占位符，真实扫描会失败。请粘贴 goofish 登录态。"
            if session.looks_like_placeholder else None
        ),
    }


def session_status(conn: sqlite3.Connection) -> dict:
    try:
        return _session_view(load_session(), paused=is_auth_paused(conn))
    except AuthError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "paused": is_auth_paused(conn),
        }


def save_session(conn: sqlite3.Connection, payload: dict[str, Any], filename: str) -> dict:
    ensure_data_dirs()
    name = Path(filename).name
    if not name.endswith(".json"):
        name += ".json"
    path = cfg.STATE_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    session = load_session(path)
    clear_auth_paused(conn)
    result = _session_view(session, paused=False)
    result["path"] = str(path)
    return result


def clear_pause(conn: sqlite3.Connection) -> dict:
    clear_auth_paused(conn)
    return {"ok": True, "paused": False}


def check_session(conn: sqlite3.Connection, session: Session, *, ping: bool = False) -> dict:
    result = _session_view(session, paused=is_auth_paused(conn))
    if not ping:
        return result
    if session.looks_like_placeholder:
        result["ping"] = "skip"
        result["ping_error"] = "placeholder cookie; refuse live ping"
        return result
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
    except Exception as exc:
        result["ping"] = "fail"
        result["ping_error"] = str(exc)
    return result

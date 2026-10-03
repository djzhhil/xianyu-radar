"""Public Helper status and verified pause recovery; no Cookie persistence."""
from __future__ import annotations

import sqlite3

from xianyu_radar.infrastructure.goofish.mtop import call_mtop
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.helper.session_provider import provider_status, session_operation
from xianyu_radar.infrastructure.storage.auth_state import auth_pause_reason, clear_auth_paused, is_auth_paused


def session_status(conn: sqlite3.Connection) -> dict:
    result = provider_status()
    result["paused"] = is_auth_paused(conn)
    result["pause_reason"] = auth_pause_reason(conn) if result["paused"] else None
    result.setdefault("hint", "登录、续期和人机验证由 Helper 管理。获取快照不代表闲鱼在线验证成功。")
    return result


def check_session(conn: sqlite3.Connection, session: Session, *, ping: bool = False) -> dict:
    if ping:
        call_mtop(session, "taobao.idlemtopsearch.pc.search", {
            "pageNumber": 1, "keyword": "test", "fromFilter": False, "rowsPerPage": 1,
            "sortValue": "", "sortField": "", "customDistance": "", "gps": "",
            "propValueStr": {}, "customGps": "", "searchReqFromPage": "pcSearch",
            "extraFilterValue": "{}", "userPositionJson": "{}",
        }, {"spm_cnt": "a21ybx.search.0.0"})
        clear_auth_paused(conn)
    return {**session_status(conn), "ping": "ok" if ping else "not_checked"}


def clear_pause(conn: sqlite3.Connection) -> dict:
    # Clearing a flag is only allowed after a fresh snapshot and online check.
    with session_operation() as session:
        return check_session(conn, session, ping=True)

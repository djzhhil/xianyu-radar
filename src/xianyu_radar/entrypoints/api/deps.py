"""Shared API helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Generator
from contextlib import contextmanager

from fastapi import HTTPException

from xianyu_radar.infrastructure.goofish.errors import AuthError, HelperError, error_kind
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.helper.session_provider import session_operation
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.auth_state import set_auth_paused


def get_db() -> Generator[sqlite3.Connection, None, None]:
    # FastAPI can resume a sync generator dependency on a different worker thread.
    conn = init_db(check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def parse_since(since: str | None) -> str | None:
    if not since:
        return None
    s = since.strip().lower()
    now = datetime.now(timezone.utc)
    if s.endswith("h") and s[:-1].isdigit():
        return (now - timedelta(hours=int(s[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
    if s.endswith("d") and s[:-1].isdigit():
        return (now - timedelta(days=int(s[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
    return since


@contextmanager
def require_session(conn: sqlite3.Connection | None = None):
    session = None
    try:
        with session_operation() as session:
            yield session
    except HelperError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.kind, "message": str(exc)}) from None
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    except MtopError as exc:
        kind = error_kind(exc)
        status = {"verification_required": 403, "rate_limit": 429, "token": 409}.get(kind, 502)
        message = {"verification_required": "闲鱼要求人机验证，请在 Helper 完成验证后重新检查。",
                   "rate_limit": "闲鱼接口限流，请稍后重试。",
                   "token": "签名 Token 恢复失败，请在 Helper 检查登录态。"}.get(kind, str(exc))
        raise HTTPException(status_code=status, detail={"code": kind, "message": message}) from None
    finally:
        if conn is not None and session is not None and session.stop_kind in {"auth", "verification_required"}:
            set_auth_paused(conn, session.stop_kind)


def event_to_dict(e) -> dict:
    return {
        "item_id": e.item_id,
        "seller_id": e.seller_id,
        "event_type": e.event_type,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "is_baseline": e.is_baseline,
    }

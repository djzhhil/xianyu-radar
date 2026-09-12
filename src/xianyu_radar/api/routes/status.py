"""Status / overview endpoints."""

from __future__ import annotations

import sqlite3

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from xianyu_radar import __version__
from xianyu_radar import config as cfg
from xianyu_radar.api.deps import get_db
from xianyu_radar.auth.session import try_load_session
from xianyu_radar.scheduler.runner import is_auth_paused
from xianyu_radar.storage.db import get_schema_version

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "env": cfg.RADAR_ENV}


@router.get("/status")
def status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    session = try_load_session()
    sellers = conn.execute(
        "SELECT COUNT(*) AS c FROM sellers WHERE status='watching'"
    ).fetchone()["c"]
    items = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
    candidates = conn.execute("SELECT COUNT(*) AS c FROM candidates").fetchone()["c"]
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events_24h = conn.execute(
        "SELECT COUNT(*) AS c FROM item_events WHERE detected_at >= ?",
        (since,),
    ).fetchone()["c"]
    keywords = conn.execute(
        "SELECT COUNT(*) AS c FROM watch_keywords WHERE enabled=1"
    ).fetchone()["c"]
    auth = {
        "ok": bool(session and session.ok),
        "source": session.source if session else None,
        "cookie_count": session.cookie_count if session else 0,
        "paused": is_auth_paused(conn),
        "looks_like_placeholder": bool(session and session.looks_like_placeholder),
        "state_dir": str(cfg.STATE_DIR),
    }
    if auth["looks_like_placeholder"]:
        auth["hint"] = "Cookie 为测试占位符，真实 MTOP 会失败；请到「登录态」粘贴真实会话。"
    elif auth["paused"]:
        auth["hint"] = "auth 已暂停（上次会话失效）。可清除暂停或更新 Cookie。"
    return {
        "version": __version__,
        "env": cfg.RADAR_ENV,
        "schema_version": get_schema_version(conn),
        "db_path": str(cfg.DB_PATH),
        "auth": auth,
        "counts": {
            "watching_sellers": sellers,
            "items": items,
            "candidates": candidates,
            "events_24h": events_24h,
            "keywords": keywords,
        },
    }

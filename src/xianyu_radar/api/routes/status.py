"""Status / overview endpoints."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from fastapi import APIRouter, Depends

from xianyu_radar import __version__
from xianyu_radar import config as cfg
from xianyu_radar.api.deps import get_db
from xianyu_radar.auth.session import auth_mode, try_load_session
from xianyu_radar.scheduler.runner import is_auth_paused
from xianyu_radar.storage.db import get_schema_version
from xianyu_radar.timeutil import since_iso

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
    since = since_iso(timedelta(hours=24))
    events_24h = conn.execute(
        "SELECT COUNT(*) AS c FROM item_events WHERE detected_at >= ?",
        (since,),
    ).fetchone()["c"]
    keywords = conn.execute(
        "SELECT COUNT(*) AS c FROM watch_keywords WHERE enabled=1"
    ).fetchone()["c"]
    mode = auth_mode()
    source = None
    if session:
        # Never put lease cookies or full lease ids into API responses.
        if session.from_broker and session.account_id:
            source = f"broker:{session.account_id}"
        else:
            source = "local" if session.source else None
    auth = {
        "ok": bool(session and session.ok),
        "source": source,
        "cookie_count": session.cookie_count if session else 0,
        "paused": is_auth_paused(conn),
        "looks_like_placeholder": bool(session and session.looks_like_placeholder),
        "state_dir": str(cfg.STATE_DIR),
        "mode": mode,
        "from_broker": bool(session and session.from_broker),
        "account_id": session.account_id if session else None,
        "lease_active": bool(session and session.lease_id),
    }
    broker_health = None
    if mode == "broker":
        try:
            from xianyu_radar.auth.broker_client import get_broker_client

            client = get_broker_client()
            if client.configured:
                raw = client.health()
                # Public status: accounts + metrics only (no event payloads).
                broker_health = {
                    "accounts": [
                        {
                            "id": a.get("id"),
                            "nickname": a.get("nickname"),
                            "enabled": a.get("enabled"),
                            "paused": a.get("paused"),
                            "health": a.get("health"),
                            "last_error_kind": a.get("last_error_kind"),
                            "lease_held": a.get("lease_held"),
                        }
                        for a in (raw.get("accounts") or [])
                        if isinstance(a, dict)
                    ],
                    "metrics": raw.get("metrics") or {},
                }
        except Exception as e:
            broker_health = {"error": str(e)}
    if auth["looks_like_placeholder"]:
        auth["hint"] = "Cookie 为测试占位符，真实 MTOP 会失败；请到「登录态」粘贴真实会话。"
    elif auth["paused"]:
        auth["hint"] = "auth 已暂停（上次会话失效或风控）。可清除暂停或更新 Cookie / 续租。"
    elif mode == "broker" and not auth["ok"]:
        auth["hint"] = "Broker 模式未拿到租约。检查 RADAR_BROKER_URL/TOKEN/ACCOUNT_ID 与 Helper 登录态。"
    return {
        "version": __version__,
        "env": cfg.RADAR_ENV,
        "schema_version": get_schema_version(conn),
        "db_path": str(cfg.DB_PATH),
        "auth": auth,
        "broker": broker_health,
        "counts": {
            "watching_sellers": sellers,
            "items": items,
            "candidates": candidates,
            "events_24h": events_24h,
            "keywords": keywords,
        },
    }

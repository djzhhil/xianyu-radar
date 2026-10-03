"""Status / overview endpoints."""

from __future__ import annotations

import sqlite3

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from xianyu_radar import __version__
from xianyu_radar import config as cfg
from xianyu_radar.entrypoints.api.deps import get_db
from xianyu_radar.infrastructure.helper.session_provider import provider_status
from xianyu_radar.infrastructure.storage.auth_state import auth_pause_reason, is_auth_paused
from xianyu_radar.infrastructure.storage.db import get_schema_version

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@router.get("/status")
def status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    sellers = conn.execute(
        "SELECT COUNT(*) AS c FROM sellers s WHERE s.status='watching' "
        "AND EXISTS (SELECT 1 FROM seller_pool_entries p WHERE p.seller_id=s.seller_id AND p.active=1)"
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
    auth = {**provider_status(), "paused": is_auth_paused(conn)}
    auth["pause_reason"] = auth_pause_reason(conn) if auth["paused"] else None
    if auth["paused"]:
        auth["hint"] = "在线工作已暂停，请在 Helper 恢复登录或验证后重新检查。"
    return {
        "version": __version__,
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

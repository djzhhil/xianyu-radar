"""Shared API helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Generator

from fastapi import HTTPException

from xianyu_radar.auth.session import AuthError, Session, load_session
from xianyu_radar.storage.db import init_db


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = init_db()
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


def require_session(state: str | None = None) -> Session:
    try:
        return load_session(state)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


def event_to_dict(e) -> dict:
    return {
        "item_id": e.item_id,
        "seller_id": e.seller_id,
        "event_type": e.event_type,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "is_baseline": e.is_baseline,
    }

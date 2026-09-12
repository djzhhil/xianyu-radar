"""Shared API helpers."""

from __future__ import annotations

import sqlite3
from typing import Generator

from fastapi import HTTPException

from xianyu_radar.auth.session import AuthError, Session, load_session
from xianyu_radar.storage.db import init_db
from xianyu_radar.timeutil import parse_relative_since


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = init_db()
    try:
        yield conn
    finally:
        conn.close()


def parse_since(since: str | None) -> str | None:
    return parse_relative_since(since)


def clamp_page(
    page: int = 1,
    page_size: int = 50,
    *,
    max_size: int = 200,
    default_size: int = 50,
) -> tuple[int, int, int]:
    """Return (page, page_size, offset) with sane bounds."""
    page = max(1, int(page or 1))
    size = int(page_size or default_size)
    page_size = min(max(size, 1), max_size)
    offset = (page - 1) * page_size
    return page, page_size, offset


def page_meta(total: int, page: int, page_size: int) -> dict:
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


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

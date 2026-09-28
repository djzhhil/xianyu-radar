"""Scan event queries."""

from __future__ import annotations

import sqlite3


def list_events(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    seller_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    sql = "SELECT * FROM item_events WHERE 1=1"
    params: list = []
    if since_iso:
        sql += " AND detected_at>=?"
        params.append(since_iso)
    if seller_id:
        sql += " AND seller_id=?"
        params.append(seller_id)
    sql += " ORDER BY detected_at DESC, id DESC LIMIT ? OFFSET ?"
    params.extend((limit, offset))
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def count_events(
    conn: sqlite3.Connection, *, since_iso: str | None = None, seller_id: str | None = None
) -> int:
    sql = "SELECT COUNT(*) FROM item_events WHERE 1=1"
    params: list[str] = []
    if since_iso:
        sql += " AND detected_at>=?"
        params.append(since_iso)
    if seller_id:
        sql += " AND seller_id=?"
        params.append(seller_id)
    return conn.execute(sql, params).fetchone()[0]

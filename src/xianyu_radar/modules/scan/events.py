"""Scan event queries."""

from __future__ import annotations

import sqlite3


def list_events(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    seller_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    sql = "SELECT * FROM item_events WHERE 1=1"
    params: list = []
    if since_iso:
        sql += " AND detected_at>=?"
        params.append(since_iso)
    if seller_id:
        sql += " AND seller_id=?"
        params.append(seller_id)
    sql += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]

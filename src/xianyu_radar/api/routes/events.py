"""Events endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from xianyu_radar.api.deps import get_db, parse_since

router = APIRouter()


@router.get("")
def get_events(
    since: str = "24h",
    seller: str | None = None,
    limit: int = 100,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    sql = "SELECT * FROM item_events WHERE 1=1"
    params: list = []
    since_iso = parse_since(since)
    if since_iso:
        sql += " AND detected_at>=?"
        params.append(since_iso)
    if seller:
        sql += " AND seller_id=?"
        params.append(seller)
    sql += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"count": len(rows), "since": since, "events": rows}

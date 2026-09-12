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
    """List events joined with item title/price/url and seller nickname."""
    sql = """
        SELECT
            e.id,
            e.item_id,
            e.seller_id,
            e.event_type,
            e.old_value,
            e.new_value,
            e.is_baseline,
            e.detected_at,
            e.scan_id,
            COALESCE(i.title, e.new_value, e.old_value, '') AS title,
            COALESCE(i.price, i.last_price, '') AS price,
            COALESCE(i.url, '') AS url,
            COALESCE(i.status, '') AS item_status,
            COALESCE(s.nickname, '') AS seller_nickname
        FROM item_events e
        LEFT JOIN items i ON i.item_id = e.item_id
        LEFT JOIN sellers s ON s.seller_id = e.seller_id
        WHERE 1=1
    """
    params: list = []
    since_iso = parse_since(since)
    if since_iso:
        sql += " AND e.detected_at>=?"
        params.append(since_iso)
    if seller:
        sql += " AND e.seller_id=?"
        params.append(seller)
    sql += " ORDER BY e.detected_at DESC LIMIT ?"
    params.append(min(max(limit, 1), 500))
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    for row in rows:
        row["is_baseline"] = bool(row.get("is_baseline"))
        if not row.get("url") and row.get("item_id"):
            row["url"] = f"https://www.goofish.com/item?id={row['item_id']}"
    return {"count": len(rows), "since": since, "events": rows}

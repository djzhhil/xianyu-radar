"""Item snapshot history endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from xianyu_radar.api.deps import clamp_page, get_db, page_meta

router = APIRouter()


@router.get("")
def list_snapshots(
    item_id: str | None = None,
    seller: str | None = None,
    page: int = 1,
    page_size: int = 50,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Paginated item snapshots (price/title at each scan)."""
    page, page_size, offset = clamp_page(page, page_size, max_size=200, default_size=50)
    where = " WHERE 1=1"
    params: list = []
    if item_id:
        where += " AND sn.item_id=?"
        params.append(item_id.strip())
    if seller:
        where += " AND sn.seller_id=?"
        params.append(seller.strip())

    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM item_snapshots sn{where}",
        params,
    ).fetchone()["c"]

    sql = f"""
        SELECT
            sn.id,
            sn.item_id,
            sn.seller_id,
            sn.title,
            sn.price,
            sn.captured_at,
            sn.scan_id,
            COALESCE(s.nickname, '') AS seller_nickname,
            COALESCE(i.url, '') AS url,
            COALESCE(i.status, '') AS item_status
        FROM item_snapshots sn
        LEFT JOIN sellers s ON s.seller_id = sn.seller_id
        LEFT JOIN items i ON i.item_id = sn.item_id
        {where}
        ORDER BY sn.captured_at DESC, sn.id DESC
        LIMIT ? OFFSET ?
    """
    rows = [
        dict(r)
        for r in conn.execute(sql, [*params, page_size, offset]).fetchall()
    ]
    for row in rows:
        if not row.get("url") and row.get("item_id"):
            row["url"] = f"https://www.goofish.com/item?id={row['item_id']}"
    meta = page_meta(total, page, page_size)
    return {
        "count": len(rows),
        "item_id": item_id,
        "seller": seller,
        "snapshots": rows,
        **meta,
    }


@router.get("/items/{item_id}")
def item_history(
    item_id: str,
    limit: int = 100,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Chronological history for one item (oldest → newest for charting)."""
    limit = min(max(limit, 1), 500)
    item = conn.execute(
        "SELECT item_id, seller_id, title, price, url, status, first_seen_at, last_seen_at "
        "FROM items WHERE item_id=?",
        (item_id,),
    ).fetchone()
    if not item:
        # still allow snapshots if item row missing
        snaps = conn.execute(
            "SELECT COUNT(*) AS c FROM item_snapshots WHERE item_id=?",
            (item_id,),
        ).fetchone()["c"]
        if not snaps:
            raise HTTPException(status_code=404, detail="item not found")
        item_info = {"item_id": item_id}
    else:
        item_info = dict(item)
        if not item_info.get("url"):
            item_info["url"] = f"https://www.goofish.com/item?id={item_id}"

    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT id, item_id, seller_id, title, price, captured_at, scan_id "
            "FROM item_snapshots WHERE item_id=? "
            "ORDER BY captured_at ASC, id ASC LIMIT ?",
            (item_id, limit),
        ).fetchall()
    ]
    return {
        "item": item_info,
        "count": len(rows),
        "snapshots": rows,
    }

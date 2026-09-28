"""Item snapshot history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from xianyu_radar.models import SellerItem


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_scan_runs(
    conn: sqlite3.Connection,
    *,
    seller_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    where = " WHERE seller_id=?" if seller_id else ""
    params = (seller_id,) if seller_id else ()
    total = conn.execute(f"SELECT COUNT(*) FROM scans{where}", params).fetchone()[0]
    rows = conn.execute(
        "SELECT id, seller_id, started_at, finished_at, status, error_kind, "
        f"item_count, event_count FROM scans{where} "
        "ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return {"total": total, "runs": [dict(row) for row in rows], "limit": limit, "offset": offset}


def write_snapshots(
    conn: sqlite3.Connection,
    seller_id: str,
    items: list[SellerItem],
    scan_id: str,
) -> None:
    now = _now()
    conn.executemany(
        "INSERT INTO item_snapshots(item_id, seller_id, title, price, captured_at, scan_id) "
        "VALUES (?,?,?,?,?,?)",
        [(i.item_id, seller_id, i.title, i.price, now, scan_id) for i in items],
    )

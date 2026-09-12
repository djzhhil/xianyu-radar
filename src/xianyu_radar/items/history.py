"""Item snapshot history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from xianyu_radar.models import SellerItem


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

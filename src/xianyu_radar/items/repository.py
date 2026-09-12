"""Item current-state repository."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from xianyu_radar.models import SellerItem


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_active_items(conn: sqlite3.Connection, seller_id: str) -> dict[str, dict]:
    """Load seller catalog for diff.

    Discovery seeds (source=discovery) are excluded so the first real shop scan
    remains a baseline even if discover already wrote those item rows.
    """
    rows = conn.execute(
        "SELECT * FROM items WHERE seller_id=? AND status='active' "
        "AND COALESCE(source,'') != 'discovery'",
        (seller_id,),
    ).fetchall()
    return {r["item_id"]: dict(r) for r in rows}


def ensure_seller(conn: sqlite3.Connection, seller_id: str) -> None:
    now = _now()
    row = conn.execute(
        "SELECT seller_id FROM sellers WHERE seller_id=?", (seller_id,)
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO sellers(seller_id, first_seen_at, last_seen_at, status) "
            "VALUES (?,?,?, 'watching')",
            (seller_id, now, now),
        )


def upsert_seller_item(
    conn: sqlite3.Connection,
    seller_id: str,
    item: SellerItem,
    *,
    bump_check: bool = True,
) -> None:
    now = _now()
    ensure_seller(conn, seller_id)
    existing = conn.execute(
        "SELECT item_id, check_count FROM items WHERE item_id=?", (item.item_id,)
    ).fetchone()
    if existing:
        check = int(existing["check_count"] or 0) + (1 if bump_check else 0)
        conn.execute(
            "UPDATE items SET seller_id=?, title=?, price=?, url=?, status='active', "
            "last_seen_at=?, last_price=?, last_title=?, check_count=?, source='seller_scan' "
            "WHERE item_id=?",
            (
                seller_id,
                item.title,
                item.price,
                item.url,
                now,
                item.price,
                item.title,
                check,
                item.item_id,
            ),
        )
    else:
        conn.execute(
            "INSERT INTO items(item_id, seller_id, title, price, url, status, first_seen_at, "
            "last_seen_at, last_price, last_title, check_count, source) "
            "VALUES (?,?,?,?,?,'active',?,?,?,?,?, 'seller_scan')",
            (
                item.item_id,
                seller_id,
                item.title,
                item.price,
                item.url,
                now,
                now,
                item.price,
                item.title,
                1 if bump_check else 0,
            ),
        )


def mark_removed(conn: sqlite3.Connection, item_id: str) -> None:
    now = _now()
    conn.execute(
        "UPDATE items SET status='removed', last_seen_at=? WHERE item_id=?",
        (now, item_id),
    )

"""Seller pool CRUD."""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone

from xianyu_radar.models import SeedItem


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_seed_item(
    conn: sqlite3.Connection,
    item: SeedItem,
    *,
    keyword: str | None = None,
) -> None:
    """Upsert an item seen during discovery. seller_id may be temporary placeholder."""
    now = _now()
    seller_id = item.seller_id or f"unknown:{item.item_id}"
    # Ensure seller row exists for FK (unknown sellers get placeholder status dropped)
    row = conn.execute(
        "SELECT seller_id FROM sellers WHERE seller_id=?", (seller_id,)
    ).fetchone()
    if not row:
        status = "watching" if item.seller_id else "dropped"
        conn.execute(
            "INSERT INTO sellers(seller_id, nickname, first_seen_at, last_seen_at, status) "
            "VALUES (?,?,?,?,?)",
            (seller_id, item.seller_nick, now, now, status),
        )
    else:
        conn.execute(
            "UPDATE sellers SET last_seen_at=?, nickname=COALESCE(?, nickname) WHERE seller_id=?",
            (now, item.seller_nick, seller_id),
        )

    existing = conn.execute(
        "SELECT item_id FROM items WHERE item_id=?", (item.item_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE items SET title=?, price=?, url=?, last_seen_at=?, last_price=?, last_title=?, "
            "seller_id=CASE WHEN ? LIKE 'unknown:%' THEN seller_id ELSE ? END WHERE item_id=?",
            (
                item.title,
                item.price,
                item.url,
                now,
                item.price,
                item.title,
                seller_id,
                seller_id,
                item.item_id,
            ),
        )
    else:
        conn.execute(
            "INSERT INTO items(item_id, seller_id, title, price, url, status, first_seen_at, "
            "last_seen_at, last_price, last_title, check_count, source) "
            "VALUES (?,?,?,?,?,'active',?,?,?,?,0,'discovery')",
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
            ),
        )


def add_seller_from_discovery(
    conn: sqlite3.Connection,
    *,
    seller_id: str,
    nickname: str | None,
    source_keyword: str | None,
    source_item_id: str | None,
    reason: str = "discovered_via_keyword",
) -> bool:
    """Return True if seller row was newly created."""
    now = _now()
    created = False
    row = conn.execute(
        "SELECT seller_id FROM sellers WHERE seller_id=?", (seller_id,)
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO sellers(seller_id, nickname, first_seen_at, last_seen_at, status) "
            "VALUES (?,?,?,?, 'watching')",
            (seller_id, nickname, now, now),
        )
        created = True
    else:
        conn.execute(
            "UPDATE sellers SET last_seen_at=?, nickname=COALESCE(?, nickname), "
            "status=CASE WHEN status='dropped' AND ? NOT LIKE 'unknown:%' THEN 'watching' ELSE status END "
            "WHERE seller_id=?",
            (now, nickname, seller_id, seller_id),
        )

    conn.execute(
        "INSERT INTO seller_pool_entries(seller_id, source_keyword, source_item_id, reason, joined_at, active) "
        "VALUES (?,?,?,?,?,1)",
        (seller_id, source_keyword, source_item_id, reason, now),
    )
    return created


def list_pool(conn: sqlite3.Connection, *, status: str | None = "watching") -> list[dict]:
    # A placeholder seller exists only to satisfy the items foreign key; it is not in the pool.
    membership = "EXISTS (SELECT 1 FROM seller_pool_entries p WHERE p.seller_id=s.seller_id AND p.active=1)"
    if status:
        rows = conn.execute(
            "SELECT s.*, "
            "(SELECT GROUP_CONCAT(DISTINCT source_keyword) FROM seller_pool_entries e "
            " WHERE e.seller_id=s.seller_id AND e.active=1) AS keywords "
            f"FROM sellers s WHERE {membership} AND s.status=? ORDER BY s.last_seen_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT s.*, "
            "(SELECT GROUP_CONCAT(DISTINCT source_keyword) FROM seller_pool_entries e "
            " WHERE e.seller_id=s.seller_id AND e.active=1) AS keywords "
            f"FROM sellers s WHERE {membership} ORDER BY s.last_seen_at DESC"
        ).fetchall()
    return [_seller_record(r) for r in rows]


def _seller_record(row: sqlite3.Row) -> dict:
    record = dict(row)
    record["tags"] = json.loads(record["tags"])
    return record


def set_seller_metadata(conn: sqlite3.Connection, seller_id: str, notes: str, tags: list[str]) -> bool:
    with conn:
        result = conn.execute(
            "UPDATE sellers SET notes=?, tags=? WHERE seller_id=? AND EXISTS ("
            "SELECT 1 FROM seller_pool_entries WHERE seller_id=? AND active=1)",
            (notes, json.dumps(tags, ensure_ascii=False), seller_id, seller_id),
        )
    return result.rowcount > 0


def add_manual_seller(conn: sqlite3.Connection, seller_id: str, nickname: str | None) -> bool:
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO sellers(seller_id, nickname, first_seen_at, last_seen_at) "
            "VALUES (?,?,?,?) ON CONFLICT(seller_id) DO NOTHING",
            (seller_id, nickname, now, now),
        )
        exists = conn.execute(
            "SELECT 1 FROM seller_pool_entries WHERE seller_id=? AND reason='manual' AND active=1",
            (seller_id,),
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO seller_pool_entries(seller_id, reason, joined_at) VALUES (?, 'manual', ?)",
            (seller_id, now),
        )
    return True


def get_pool_seller_detail(
    conn: sqlite3.Connection, seller_id: str, *, limit: int = 20, offset: int = 0,
    query: str = "", item_status: str = ""
) -> dict | None:
    """Read one pool seller, its discovery sources, and stored catalog page."""
    seller = conn.execute(
        "SELECT s.*, "
        "(SELECT GROUP_CONCAT(DISTINCT source_keyword) FROM seller_pool_entries e "
        " WHERE e.seller_id=s.seller_id AND e.active=1) AS keywords "
        "FROM sellers s WHERE s.seller_id=? AND EXISTS ("
        " SELECT 1 FROM seller_pool_entries e WHERE e.seller_id=s.seller_id AND e.active=1)",
        (seller_id,),
    ).fetchone()
    if seller is None:
        return None
    entries = conn.execute(
        "SELECT id, source_keyword, source_item_id, reason, joined_at, active "
        "FROM seller_pool_entries WHERE seller_id=? ORDER BY joined_at DESC, id DESC",
        (seller_id,),
    ).fetchall()
    conditions = ["seller_id=?"]
    params: list[object] = [seller_id]
    if query:
        conditions.append("instr(lower(COALESCE(title,'')),lower(?)) > 0")
        params.append(query)
    if item_status:
        conditions.append("status=?")
        params.append(item_status)
    where = " AND ".join(conditions)
    total_items = conn.execute("SELECT COUNT(*) FROM items WHERE " + where, params).fetchone()[0]
    items = conn.execute(
        "SELECT item_id, title, price, url, image, category, status, first_seen_at, "
        "last_seen_at, check_count, source FROM items WHERE " + where + " "
        "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, "
        "last_seen_at DESC, item_id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    scan_columns = "id, started_at, finished_at, status, error_kind, item_count, page_count, finish_reason"
    latest = conn.execute(
        "SELECT " + scan_columns + " FROM scans WHERE seller_id=? ORDER BY rowid DESC LIMIT 1",
        (seller_id,),
    ).fetchone()
    complete = conn.execute(
        "SELECT " + scan_columns + " FROM scans WHERE seller_id=? AND status='ok' ORDER BY rowid DESC LIMIT 1",
        (seller_id,),
    ).fetchone()
    return {
        "seller": _seller_record(seller),
        "entries": [dict(row) for row in entries],
        "items": [dict(row) for row in items],
        "total_items": total_items,
        "limit": limit,
        "offset": offset,
        "latest_scan": dict(latest) if latest else None,
        "latest_complete_scan": dict(complete) if complete else None,
    }


def set_seller_status(conn: sqlite3.Connection, seller_id: str, status: str) -> bool:
    cursor = conn.execute(
        "UPDATE sellers SET status=? WHERE seller_id=?",
        (status, seller_id),
    )
    conn.commit()
    return cursor.rowcount > 0

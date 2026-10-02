"""Shared candidate writes; callers own the write transaction."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from xianyu_radar.models import SellerItem


def normalize_title(title: str) -> str:
    title = title.replace("\u3000", " ").strip().lower()
    return re.sub(r"[\s\[\]【】()（）\-_/\\|]+", "", title)


def add_candidate_source(
    conn: sqlite3.Connection, seller_id: str, item: SellerItem, *,
    source_type: str, scan_id: str | None = None, observed_at: str | None = None,
) -> dict:
    existing = conn.execute(
        "SELECT candidate_id,source_id FROM candidate_sources WHERE seller_id=? AND item_id=? AND source_type=?",
        (seller_id, item.item_id, source_type),
    ).fetchone()
    if existing:
        return {"candidate_id": existing["candidate_id"], "added": False}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    norm = normalize_title(item.title) or f"item:{item.item_id}"
    row = conn.execute("SELECT candidate_id FROM candidates WHERE normalized_title=?", (norm,)).fetchone()
    if row:
        candidate_id = row["candidate_id"]
        conn.execute(
            "UPDATE candidates SET last_seen_at=?,appearance_count=appearance_count+1,"
            "sample_item_id=?,sample_title=?,sample_price=?,sample_url=? WHERE candidate_id=?",
            (now, item.item_id, item.title, item.price, item.url, candidate_id),
        )
    else:
        cursor = conn.execute(
            "INSERT INTO candidates(normalized_title,sample_item_id,sample_title,sample_price,sample_url,"
            "first_seen_at,last_seen_at,appearance_count) VALUES (?,?,?,?,?,?,?,1)",
            (norm, item.item_id, item.title, item.price, item.url, now, now),
        )
        candidate_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO candidate_sources(candidate_id,seller_id,item_id,source_type,scan_id,title,price,url,image,observed_at,added_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (candidate_id, seller_id, item.item_id, source_type, scan_id, item.title, item.price, item.url, item.image, observed_at or now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO candidate_sellers(candidate_id,seller_id,first_item_id,first_seen_at) VALUES (?,?,?,?)",
        (candidate_id, seller_id, item.item_id, now),
    )
    conn.execute(
        "UPDATE candidates SET seller_count=(SELECT COUNT(*) FROM candidate_sellers WHERE candidate_id=?),"
        "score=(SELECT COUNT(*) FROM candidate_sellers WHERE candidate_id=?)+appearance_count WHERE candidate_id=?",
        (candidate_id, candidate_id, candidate_id),
    )
    return {"candidate_id": candidate_id, "added": True}

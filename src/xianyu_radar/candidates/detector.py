"""Candidate detection and scoring."""

from __future__ import annotations

import re
import sqlite3

from xianyu_radar.models import ItemEvent, SellerItem
from xianyu_radar.timeutil import now_iso as _now


def normalize_title(title: str) -> str:
    t = title.replace("\u3000", " ").strip().lower()
    t = re.sub(r"\s+", "", t)
    # drop common punctuation
    t = re.sub(r"[\s\[\]【】()（）\-_/\\|]+", "", t)
    return t


def is_target_product(title: str, keyword_hints: list[str] | None) -> bool:
    """True if this looks like the original monitored keyword product."""
    if not keyword_hints:
        return False
    norm = normalize_title(title)
    for kw in keyword_hints:
        k = normalize_title(kw)
        if k and k in norm:
            return True
    return False


def process_new_item_events(
    conn: sqlite3.Connection,
    events: list[ItemEvent],
    *,
    current_by_id: dict[str, SellerItem],
    keyword_hints: list[str] | None = None,
) -> dict:
    added = 0
    skipped_baseline = 0
    skipped_target = 0
    for e in events:
        if e.event_type != "NEW_ITEM":
            continue
        if e.is_baseline:
            skipped_baseline += 1
            continue
        item = current_by_id.get(e.item_id)
        title = item.title if item else (e.new_value or "")
        if is_target_product(title, keyword_hints):
            skipped_target += 1
            continue
        _upsert_candidate(conn, e.seller_id, item or SellerItem(
            item_id=e.item_id, title=title, price="", url=""
        ))
        added += 1
    return {
        "added": added,
        "skipped_baseline": skipped_baseline,
        "skipped_target": skipped_target,
    }


def _upsert_candidate(conn: sqlite3.Connection, seller_id: str, item: SellerItem) -> None:
    now = _now()
    norm = normalize_title(item.title) or f"item:{item.item_id}"
    row = conn.execute(
        "SELECT candidate_id, seller_count, appearance_count FROM candidates WHERE normalized_title=?",
        (norm,),
    ).fetchone()
    if row:
        cid = row["candidate_id"]
        conn.execute(
            "UPDATE candidates SET last_seen_at=?, appearance_count=appearance_count+1, "
            "sample_item_id=?, sample_title=?, sample_price=?, sample_url=?, "
            "score = (seller_count * 1.0 + appearance_count + 1) "
            "WHERE candidate_id=?",
            (now, item.item_id, item.title, item.price, item.url, cid),
        )
    else:
        cur = conn.execute(
            "INSERT INTO candidates(normalized_title, sample_item_id, sample_title, sample_price, "
            "sample_url, first_seen_at, last_seen_at, seller_count, appearance_count, score, status) "
            "VALUES (?,?,?,?,?,?,?,0,1,1,'new')",
            (norm, item.item_id, item.title, item.price, item.url, now, now),
        )
        cid = cur.lastrowid

    link = conn.execute(
        "SELECT 1 FROM candidate_sellers WHERE candidate_id=? AND seller_id=?",
        (cid, seller_id),
    ).fetchone()
    if not link:
        conn.execute(
            "INSERT INTO candidate_sellers(candidate_id, seller_id, first_item_id, first_seen_at) "
            "VALUES (?,?,?,?)",
            (cid, seller_id, item.item_id, now),
        )
        conn.execute(
            "UPDATE candidates SET seller_count = ("
            "  SELECT COUNT(*) FROM candidate_sellers WHERE candidate_id=?"
            "), score = ("
            "  SELECT COUNT(*) FROM candidate_sellers WHERE candidate_id=?"
            ") * 1.0 + appearance_count WHERE candidate_id=?",
            (cid, cid, cid),
        )


def list_candidates(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    offset = max(offset, 0)
    limit = min(max(limit, 1), 200)
    if since_iso:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM candidates WHERE last_seen_at >= ?",
            (since_iso,),
        ).fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM candidates WHERE last_seen_at >= ? "
            "ORDER BY score DESC, last_seen_at DESC LIMIT ? OFFSET ?",
            (since_iso, limit, offset),
        ).fetchall()
    else:
        total = conn.execute("SELECT COUNT(*) AS c FROM candidates").fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM candidates ORDER BY score DESC, last_seen_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        sellers = conn.execute(
            "SELECT seller_id FROM candidate_sellers WHERE candidate_id=?",
            (d["candidate_id"],),
        ).fetchall()
        d["source_sellers"] = [s["seller_id"] for s in sellers]
        out.append(d)
    return out, total

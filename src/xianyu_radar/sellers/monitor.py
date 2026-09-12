"""Scan one seller: fetch → diff → persist → candidates."""

from __future__ import annotations

import sqlite3
import uuid

from xianyu_radar.auth.mtop import MtopError
from xianyu_radar.auth.session import AuthError, Session
from xianyu_radar.candidates.detector import process_new_item_events
from xianyu_radar.config import MAX_CONSECUTIVE_FAILURES
from xianyu_radar.items.diff import diff_items
from xianyu_radar.items.history import write_snapshots
from xianyu_radar.items.repository import load_active_items, mark_removed, upsert_seller_item
from xianyu_radar.models import ItemEvent, SellerItem
from xianyu_radar.sellers.fetcher import get_seller_items
from xianyu_radar.timeutil import now_iso as _now


def _write_events(conn: sqlite3.Connection, events: list[ItemEvent], scan_id: str) -> None:
    now = _now()
    conn.executemany(
        "INSERT INTO item_events(item_id, seller_id, event_type, old_value, new_value, "
        "is_baseline, detected_at, scan_id) VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                e.item_id,
                e.seller_id,
                e.event_type,
                e.old_value,
                e.new_value,
                1 if e.is_baseline else 0,
                now,
                scan_id,
            )
            for e in events
        ],
    )


def apply_scan_result(
    conn: sqlite3.Connection,
    seller_id: str,
    current: list[SellerItem],
    *,
    scan_id: str | None = None,
    keyword_hints: list[str] | None = None,
) -> dict:
    """
    Apply an already-fetched catalog to DB (testable offline).
    Empty current → failed empty, no REMOVED.
    """
    scan_id = scan_id or f"scan_{uuid.uuid4().hex[:12]}"
    started = _now()
    conn.execute(
        "INSERT INTO scans(id, seller_id, started_at, status) VALUES (?,?,?, 'running')",
        (scan_id, seller_id, started),
    )

    if not current:
        conn.execute(
            "UPDATE scans SET finished_at=?, status='failed', error_kind='empty' WHERE id=?",
            (_now(), scan_id),
        )
        conn.execute(
            "UPDATE sellers SET consecutive_failures = consecutive_failures + 1 WHERE seller_id=?",
            (seller_id,),
        )
        row = conn.execute(
            "SELECT consecutive_failures FROM sellers WHERE seller_id=?", (seller_id,)
        ).fetchone()
        if row and int(row["consecutive_failures"]) >= MAX_CONSECUTIVE_FAILURES:
            conn.execute(
                "UPDATE sellers SET status='paused' WHERE seller_id=?", (seller_id,)
            )
        conn.commit()
        return {
            "scan_id": scan_id,
            "status": "failed",
            "error_kind": "empty",
            "events": [],
            "item_count": 0,
        }

    previous = load_active_items(conn, seller_id)
    events = diff_items(seller_id, previous, current, allow_removed=True)

    for item in current:
        upsert_seller_item(conn, seller_id, item, bump_check=True)
    write_snapshots(conn, seller_id, current, scan_id)

    for e in events:
        if e.event_type == "REMOVED_ITEM":
            mark_removed(conn, e.item_id)

    _write_events(conn, events, scan_id)
    cand_stats = process_new_item_events(
        conn, events, current_by_id={i.item_id: i for i in current}, keyword_hints=keyword_hints
    )

    conn.execute(
        "UPDATE sellers SET last_scan_at=?, consecutive_failures=0, last_seen_at=? WHERE seller_id=?",
        (_now(), _now(), seller_id),
    )
    conn.execute(
        "UPDATE scans SET finished_at=?, status='ok', item_count=?, event_count=? WHERE id=?",
        (_now(), len(current), len(events), scan_id),
    )
    conn.commit()
    return {
        "scan_id": scan_id,
        "status": "ok",
        "item_count": len(current),
        "events": events,
        "candidates": cand_stats,
    }


def scan_seller(
    conn: sqlite3.Connection,
    session: Session,
    seller_id: str,
    *,
    keyword_hints: list[str] | None = None,
) -> dict:
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    try:
        items = get_seller_items(session, seller_id)
    except AuthError as e:
        conn.execute(
            "INSERT INTO scans(id, seller_id, started_at, finished_at, status, error_kind) "
            "VALUES (?,?,?,?, 'failed', 'auth')",
            (scan_id, seller_id, _now(), _now()),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused', '1')"
        )
        conn.commit()
        return {"scan_id": scan_id, "status": "failed", "error_kind": "auth", "error": str(e)}
    except MtopError as e:
        kind = "rate_limit" if ("VALIDATE" in str(e) or "rate limited" in str(e).lower()) else "network"
        conn.execute(
            "INSERT INTO scans(id, seller_id, started_at, finished_at, status, error_kind) "
            "VALUES (?,?,?,?, 'failed', ?)",
            (scan_id, seller_id, _now(), _now(), kind),
        )
        conn.execute(
            "UPDATE sellers SET consecutive_failures = consecutive_failures + 1 WHERE seller_id=?",
            (seller_id,),
        )
        # VALIDATE / RGV587: pause whole pool like auth failure to avoid hammering.
        if kind == "rate_limit":
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused', '1')"
            )
            conn.commit()
            return {
                "scan_id": scan_id,
                "status": "failed",
                "error_kind": "auth",
                "error": str(e),
            }
        conn.commit()
        return {"scan_id": scan_id, "status": "failed", "error_kind": kind, "error": str(e)}

    # attach keyword hints from pool if not provided
    if keyword_hints is None:
        rows = conn.execute(
            "SELECT DISTINCT source_keyword FROM seller_pool_entries "
            "WHERE seller_id=? AND active=1 AND source_keyword IS NOT NULL",
            (seller_id,),
        ).fetchall()
        keyword_hints = [r["source_keyword"] for r in rows if r["source_keyword"]]

    return apply_scan_result(
        conn, seller_id, items, scan_id=scan_id, keyword_hints=keyword_hints
    )

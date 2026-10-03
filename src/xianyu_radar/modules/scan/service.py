"""Scan one seller: fetch → diff → persist → candidates."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.errors import HelperError, error_kind
from xianyu_radar.infrastructure.storage.auth_state import set_auth_paused
from xianyu_radar.infrastructure.goofish.session import AuthError, Session
from xianyu_radar.modules.scan.candidate_detector import process_new_item_events
from xianyu_radar.config import MAX_CONSECUTIVE_FAILURES
from xianyu_radar.modules.scan.diff import diff_items
from xianyu_radar.modules.scan.history import write_snapshots
from xianyu_radar.modules.scan.item_repository import (
    increment_missing,
    load_active_items,
    mark_removed,
    mark_unseen_seed_items_unknown,
    upsert_seller_item,
)
from xianyu_radar.models import ItemEvent, SellerItem
from xianyu_radar.modules.scan.fetcher import get_seller_items
from xianyu_radar.modules.scan.events import count_events, list_events
from xianyu_radar.modules.scan.models import SellerCatalog
from xianyu_radar.modules.scan.locks import seller_scan_lock


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    catalog: SellerCatalog | None = None,
    missing_increment: int = 1,
) -> dict:
    """
    Apply an already-fetched catalog to DB.
    Empty current → failed empty, no REMOVED.
    """
    scan_id = scan_id or f"scan_{uuid.uuid4().hex[:12]}"
    started = _now()
    prior_success = conn.execute(
        "SELECT item_count FROM scans WHERE seller_id=? AND status='ok' "
        "ORDER BY rowid DESC LIMIT 1",
        (seller_id,),
    ).fetchone()
    baseline = prior_success is None
    conn.execute(
        "INSERT INTO scans(id, seller_id, started_at, status, expected_count, page_count, finish_reason) "
        "VALUES (?,?,?, 'running',?,?,?)",
        (
            scan_id, seller_id, started,
            catalog.expected_count if catalog else None,
            catalog.page_count if catalog else None,
            catalog.finish_reason if catalog else None,
        ),
    )

    confirmed_empty = (
        not baseline and not current and catalog is not None
        and catalog.complete and catalog.expected_count == 0
        and (missing_increment >= 2 or int(prior_success["item_count"]) == 0)
    )
    if not current and not confirmed_empty:
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
    events = diff_items(
        seller_id, previous, current, baseline=baseline,
        allow_removed=True, missing_increment=missing_increment,
    )

    if baseline:
        mark_unseen_seed_items_unknown(conn, seller_id, {item.item_id for item in current})

    for item in current:
        upsert_seller_item(conn, seller_id, item, bump_check=True)
    if not baseline:
        increment_missing(
            conn, set(previous) - {item.item_id for item in current},
            increment=missing_increment,
        )
    write_snapshots(conn, seller_id, current, scan_id)

    for e in events:
        if e.event_type == "REMOVED_ITEM":
            mark_removed(conn, e.item_id)

    _write_events(conn, events, scan_id)
    cand_stats = process_new_item_events(
        conn, events, current_by_id={i.item_id: i for i in current}, keyword_hints=keyword_hints, scan_id=scan_id
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
        "expected_count": catalog.expected_count if catalog else None,
        "page_count": catalog.page_count if catalog else None,
        "finish_reason": catalog.finish_reason if catalog else None,
    }


def _record_untrusted_catalog(
    conn: sqlite3.Connection,
    scan_id: str,
    seller_id: str,
    catalog: SellerCatalog,
    *,
    status: str,
    error_kind: str,
) -> dict:
    conn.execute(
        "INSERT INTO scans(id, seller_id, started_at, finished_at, status, error_kind, "
        "item_count, expected_count, page_count, finish_reason) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            scan_id, seller_id, _now(), _now(), status, error_kind,
            len(catalog.items), catalog.expected_count, catalog.page_count,
            catalog.finish_reason,
        ),
    )
    if status == "suspect":
        write_snapshots(conn, seller_id, catalog.items, scan_id)
    conn.commit()
    return {
        "scan_id": scan_id, "status": status, "error_kind": error_kind,
        "item_count": len(catalog.items), "events": [],
        "expected_count": catalog.expected_count,
        "page_count": catalog.page_count,
        "finish_reason": catalog.finish_reason,
    }


def scan_seller(
    conn: sqlite3.Connection,
    session: Session,
    seller_id: str,
    *,
    keyword_hints: list[str] | None = None,
) -> dict:
    with seller_scan_lock(seller_id) as acquired:
        if not acquired:
            return {
                "status": "skipped", "error_kind": "already_running",
                "item_count": 0, "events": [],
            }
        return _scan_seller_unlocked(
            conn, session, seller_id, keyword_hints=keyword_hints
        )


def _scan_seller_unlocked(
    conn: sqlite3.Connection,
    session: Session,
    seller_id: str,
    *,
    keyword_hints: list[str] | None = None,
) -> dict:
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    def save_page(page: dict) -> None:
        conn.execute(
            "INSERT INTO scan_pages(scan_id, page_number, total_type, total_value, "
            "card_count, parsed_count, next_field, next_page, unique_count) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (scan_id, page["page_number"], page["total_type"], page["total_value"],
             page["card_count"], page["parsed_count"], page["next_field"],
             page["next_page"], page["unique_count"]),
        )
        conn.commit()
    try:
        catalog = get_seller_items(session, seller_id, on_page=save_page)
    except AuthError as e:
        conn.execute(
            "INSERT INTO scans(id, seller_id, started_at, finished_at, status, error_kind) "
            "VALUES (?,?,?,?, 'failed', 'auth')",
            (scan_id, seller_id, _now(), _now()),
        )
        set_auth_paused(conn, "auth")
        conn.commit()
        return {"scan_id": scan_id, "status": "failed", "error_kind": "auth", "error": str(e)}
    except (MtopError, HelperError) as e:
        kind = error_kind(e)
        conn.execute(
            "INSERT INTO scans(id, seller_id, started_at, finished_at, status, error_kind) "
            "VALUES (?,?,?,?, 'failed', ?)",
            (scan_id, seller_id, _now(), _now(), kind),
        )
        if kind == "verification_required":
            set_auth_paused(conn, kind)
        if not isinstance(e, HelperError):
            conn.execute(
                "UPDATE sellers SET consecutive_failures = consecutive_failures + 1 WHERE seller_id=?",
                (seller_id,),
            )
        conn.commit()
        return {"scan_id": scan_id, "status": "failed", "error_kind": kind, "error": str(e)}

    if not catalog.complete:
        return _record_untrusted_catalog(
            conn, scan_id, seller_id, catalog, status="failed", error_kind="incomplete"
        )

    current_ids = {item.item_id for item in catalog.items}
    latest = conn.execute(
        "SELECT id, status, error_kind FROM scans WHERE seller_id=? ORDER BY rowid DESC LIMIT 1",
        (seller_id,),
    ).fetchone()
    prior_ok = conn.execute(
        "SELECT item_count FROM scans WHERE seller_id=? AND status='ok' "
        "ORDER BY rowid DESC LIMIT 1",
        (seller_id,),
    ).fetchone()
    prior_count = int(prior_ok["item_count"]) if prior_ok else 0
    large_drop = prior_count >= 20 and len(catalog.items) * 2 < prior_count
    confirmed_drop = False
    if large_drop and latest and latest["status"] == "suspect" and latest["error_kind"] == "count_drop":
        previous_observation = {
            row["item_id"] for row in conn.execute(
                "SELECT item_id FROM item_snapshots WHERE scan_id=?", (latest["id"],)
            )
        }
        confirmed_drop = previous_observation == current_ids
    if large_drop and not confirmed_drop:
        return _record_untrusted_catalog(
            conn, scan_id, seller_id, catalog, status="suspect", error_kind="count_drop"
        )

    # attach keyword hints from pool if not provided
    if keyword_hints is None:
        rows = conn.execute(
            "SELECT DISTINCT source_keyword FROM seller_pool_entries "
            "WHERE seller_id=? AND active=1 AND source_keyword IS NOT NULL",
            (seller_id,),
        ).fetchall()
        keyword_hints = [r["source_keyword"] for r in rows if r["source_keyword"]]

    return apply_scan_result(
        conn, seller_id, catalog.items, scan_id=scan_id, keyword_hints=keyword_hints,
        catalog=catalog, missing_increment=2 if confirmed_drop else 1,
    )

"""Paged seller discovery with resumable work and redacted diagnostics."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery, upsert_seed_item
from xianyu_radar.models import SeedItem
from xianyu_radar.modules.discovery.keyword_search import search
from xianyu_radar.modules.discovery.pagination import following_page
from xianyu_radar.modules.discovery.diagnostics import error_kind_for, search_diagnostic
from xianyu_radar.modules.discovery.enrichment import enrich_pending


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_discovery_runs(conn: sqlite3.Connection, *, limit: int = 20, offset: int = 0) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM discovery_runs").fetchone()[0]
    rows = conn.execute(
        "SELECT id, keyword, started_at, finished_at, item_count, seller_count, status, "
        "error_kind, page_count, raw_result_count, unique_item_count, unique_seller_count, "
        "enriched_count, unresolved_count, unparsed_count, next_page, max_pages "
        "FROM discovery_runs ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return {"total": total, "runs": [dict(row) for row in rows], "limit": limit, "offset": offset}


def _revoke_discovery_item(conn: sqlite3.Connection, row: sqlite3.Row, reason: str) -> None:
    if row["pool_entry_id"]:
        conn.execute("UPDATE seller_pool_entries SET active=0 WHERE id=?", (row["pool_entry_id"],))
        other_source = conn.execute(
            "SELECT 1 FROM seller_pool_entries WHERE source_item_id=? AND active=1 LIMIT 1",
            (row["item_id"],),
        ).fetchone()
        if not other_source:
            conn.execute(
                "UPDATE items SET status='unknown' WHERE item_id=? AND seller_id=? "
                "AND source='discovery'", (row["item_id"], row["seller_id"]),
            )
    conn.execute(
        "UPDATE discovery_items SET seller_id=NULL, resolution='unresolved', error_kind=?, "
        "pooled=0, pool_entry_id=NULL WHERE run_id=? AND item_id=?",
        (reason, row["run_id"], row["item_id"]),
    )


def _save_page(conn: sqlite3.Connection, run_id: str, page: int, found: list[SeedItem],
               raw_count: int, entries: list | None, signal: object, result_type: str) -> int:
    before = conn.execute("SELECT COUNT(*) FROM discovery_items WHERE run_id=?", (run_id,)).fetchone()[0]
    for item in found:
        diagnostic = search_diagnostic(item, run_id)
        info = json.loads(diagnostic)
        ambiguous_image = False
        if item.seller_id:
            same_candidate = conn.execute(
                "SELECT run_id, item_id, seller_id, diagnostic, pool_entry_id FROM discovery_items "
                "WHERE run_id=? AND seller_id=?", (run_id, item.seller_id),
            ).fetchall()
            for prior in same_candidate:
                prior_info = json.loads(prior["diagnostic"])
                if prior_info.get("group_ref") == info["group_ref"]:
                    continue
                if prior_info.get("source") == "image_path":
                    _revoke_discovery_item(conn, prior, "ambiguous_image")
                if info["source"] == "image_path":
                    ambiguous_image = True
            if ambiguous_image:
                item.seller_id = None
        existing = conn.execute(
            "SELECT run_id, item_id, seller_id, error_kind, pool_entry_id "
            "FROM discovery_items WHERE run_id=? AND item_id=?",
            (run_id, item.item_id),
        ).fetchone()
        if existing:
            if existing["seller_id"] and item.seller_id and existing["seller_id"] != item.seller_id:
                _revoke_discovery_item(conn, existing, "conflicting_seller")
            elif not existing["seller_id"] and existing["error_kind"] in (None, "ambiguous_image") and item.seller_id:
                conn.execute(
                    "UPDATE discovery_items SET seller_id=?, resolution='search', "
                    "error_kind=NULL, diagnostic=? "
                    "WHERE run_id=? AND item_id=?",
                    (item.seller_id, diagnostic, run_id, item.item_id),
                )
            continue
        conn.execute(
            "INSERT INTO discovery_items(run_id, item_id, title, price, url, seller_nick, "
            "seller_id, resolution, error_kind, diagnostic) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, item.item_id, item.title, item.price, item.url, item.seller_nick,
             item.seller_id, "search" if item.seller_id else "unresolved" if ambiguous_image else "pending",
             "ambiguous_image" if ambiguous_image else None, diagnostic),
        )
    if entries is not None:
        parsed = {id(item.raw): item.item_id for item in found}
        for index, entry in enumerate(entries):
            item_id = parsed.get(id(entry))
            item_ref = hashlib.sha256(f"{run_id}:{item_id}".encode()).hexdigest() if item_id else None
            prior = conn.execute(
                "SELECT 1 FROM discovery_entries WHERE run_id=? AND item_ref=? LIMIT 1",
                (run_id, item_ref),
            ).fetchone() if item_ref else None
            conn.execute(
                "INSERT INTO discovery_entries(run_id, page_number, entry_index, outcome, item_ref) "
                "VALUES (?,?,?,?,?)",
                (run_id, page, index, "missing_item_id" if not item_id else "duplicate" if prior else "parsed",
                 item_ref),
            )
    unique = conn.execute("SELECT COUNT(*) FROM discovery_items WHERE run_id=?", (run_id,)).fetchone()[0]
    safe_signal = str(signal) if isinstance(signal, (bool, int)) or (
        isinstance(signal, str) and (signal.isdigit() or signal.lower() in {"true", "false"})
    ) else None
    conn.execute(
        "INSERT INTO discovery_pages(run_id, page_number, raw_count, parsed_count, unique_count, "
        "next_page, result_type) VALUES (?,?,?,?,?,?,?)",
        (run_id, page, raw_count, len(found), unique, safe_signal, result_type),
    )
    conn.execute(
        "UPDATE discovery_runs SET next_page=?, page_count=page_count+1, "
        "raw_result_count=raw_result_count+? WHERE id=?",
        (page + 1, raw_count, run_id),
    )
    conn.commit()
    return unique - before


def _finish(conn: sqlite3.Connection, run_id: str, keyword: str,
            status: str, error_kind: str | None) -> dict:
    conn.execute(
        "INSERT OR IGNORE INTO watch_keywords(keyword, exclude_patterns, enabled, created_at) "
        "VALUES (?, NULL, 1, ?)", (keyword, _now()),
    )
    rows = conn.execute("SELECT * FROM discovery_items WHERE run_id=?", (run_id,)).fetchall()
    new_sellers = 0
    items = []
    for row in rows:
        item = SeedItem(row["item_id"], row["title"], row["price"], row["url"],
                        row["seller_id"], row["seller_nick"])
        items.append(item)
        if item.seller_id and not row["pooled"]:
            if add_seller_from_discovery(
                conn, seller_id=item.seller_id, nickname=item.seller_nick,
                source_keyword=keyword, source_item_id=item.item_id,
            ):
                new_sellers += 1
            pool_entry_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            upsert_seed_item(conn, item, keyword=keyword)
            conn.execute(
                "UPDATE discovery_items SET pooled=1, pool_entry_id=? "
                "WHERE run_id=? AND item_id=?", (pool_entry_id, run_id, item.item_id),
            )
    unique_sellers = len({item.seller_id for item in items if item.seller_id})
    unresolved = sum(not item.seller_id for item in items)
    unparsed = conn.execute(
        "SELECT COUNT(*) FROM discovery_entries WHERE run_id=? AND outcome='missing_item_id'",
        (run_id,),
    ).fetchone()[0]
    enriched = sum(row["resolution"] == "detail" for row in rows)
    conn.execute(
        "UPDATE discovery_runs SET finished_at=?, item_count=?, unique_item_count=?, "
        "seller_count=seller_count+?, unique_seller_count=?, enriched_count=?, "
        "unresolved_count=?, unparsed_count=?, status=?, error_kind=? WHERE id=?",
        (_now(), len(items), len(items), new_sellers, unique_sellers, enriched,
         unresolved, unparsed, status, error_kind, run_id),
    )
    conn.commit()
    run = conn.execute(
        "SELECT page_count, raw_result_count, next_page, seller_count FROM discovery_runs WHERE id=?",
        (run_id,),
    ).fetchone()
    return {
        "run_id": run_id, "keyword": keyword, "status": status, "error_kind": error_kind,
        "item_count": len(items), "page_count": run["page_count"],
        "raw_result_count": run["raw_result_count"], "unique_seller_count": unique_sellers,
        "enriched": enriched, "validation_required": error_kind == "verification_required",
        "skipped_no_seller": unresolved, "new_sellers": run["seller_count"],
        "unparsed_count": unparsed,
        "next_page": run["next_page"], "items": items,
    }


def discover_sellers(
    conn: sqlite3.Connection, keyword: str, *, session: Session,
    enrich: bool = True, max_enrich: int = 30, max_pages: int = 3,
    resume_run_id: str | None = None, rows_per_page: int = 30,
) -> dict:
    """Search bounded pages, persist each page, and resume pending detail work."""
    if not 1 <= max_pages <= 50 or rows_per_page < 1 or max_enrich < 0:
        raise ValueError("invalid discovery limits")
    if resume_run_id:
        run = conn.execute("SELECT * FROM discovery_runs WHERE id=?", (resume_run_id,)).fetchone()
        if not run or run["keyword"] != keyword or run["status"] == "ok":
            raise ValueError("discovery run cannot be resumed")
        run_id = resume_run_id
        page = run["next_page"]
        conn.execute(
            "UPDATE discovery_runs SET status='running', error_kind=NULL, "
            "finished_at=NULL, max_pages=? WHERE id=?", (max_pages, run_id),
        )
        conn.execute(
            "UPDATE discovery_items SET resolution='pending', error_kind=NULL "
            "WHERE run_id=? AND seller_id IS NULL AND error_kind IN "
            "('verification_required', 'rate_limit', 'auth', 'network', 'parse_failed', "
            "'seller_id_missing', 'enrichment_disabled', 'enrichment_limit', "
            "'ambiguous_image', 'conflicting_seller')",
            (run_id,),
        )
    else:
        run_id = f"disc_{uuid.uuid4().hex[:12]}"
        page = 1
        conn.execute(
            "INSERT INTO discovery_runs(id, keyword, started_at, status, max_pages) "
            "VALUES (?,?,?,'running',?)", (run_id, keyword, _now(), max_pages),
        )
    conn.commit()
    error_kind = None
    caught: Exception | None = None
    while page and page <= max_pages:
        try:
            found = search(keyword, session) if page == 1 else search(keyword, session, page_number=page)
            raw_count = getattr(found, "raw_count", len(found))
            following, page_error = following_page(found, page, rows_per_page)
            added = _save_page(
                conn, run_id, page, found, raw_count,
                getattr(found, "entries", None), getattr(found, "next_page", None),
                getattr(found, "result_type", "mock"),
            )
            if page_error:
                error_kind = page_error
                break
            if raw_count and added == 0:
                error_kind = "duplicate_page"
                break
            page = following
            conn.execute("UPDATE discovery_runs SET next_page=? WHERE id=?", (page, run_id))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            error_kind, caught = error_kind_for(exc), exc
            break
    if page and page > max_pages and error_kind is None:
        error_kind = "page_limit"

    if enrich:
        error_kind, caught = enrich_pending(
            conn, run_id, session=session, max_enrich=max_enrich,
            error_kind=error_kind, caught=caught,
        )
    if error_kind in {"rate_limit", "verification_required", "auth"}:
        conn.execute(
            "UPDATE discovery_items SET resolution='blocked', error_kind=? "
            "WHERE run_id=? AND seller_id IS NULL AND error_kind IS NULL",
            (error_kind, run_id),
        )
    elif not enrich:
        conn.execute(
            "UPDATE discovery_items SET resolution='not_enriched', "
            "error_kind='enrichment_disabled' WHERE run_id=? AND seller_id IS NULL "
            "AND error_kind IS NULL", (run_id,),
        )
    else:
        conn.execute(
            "UPDATE discovery_items SET error_kind='enrichment_limit' "
            "WHERE run_id=? AND seller_id IS NULL AND error_kind IS NULL", (run_id,),
        )
    conn.commit()
    rows = conn.execute("SELECT seller_id, error_kind FROM discovery_items WHERE run_id=?", (run_id,)).fetchall()
    unresolved = sum(not row["seller_id"] for row in rows)
    unparsed = conn.execute(
        "SELECT COUNT(*) FROM discovery_entries WHERE run_id=? AND outcome='missing_item_id'",
        (run_id,),
    ).fetchone()[0]
    if error_kind is None and unparsed:
        error_kind = "parse_failed"
    if error_kind is None and any(row["error_kind"] == "network" for row in rows):
        error_kind = "network"
    if error_kind is None and unresolved:
        error_kind = "unresolved_items"
    if error_kind in {"rate_limit", "verification_required", "auth"}:
        status = error_kind
    elif error_kind == "network":
        status = "partial" if any(row["seller_id"] for row in rows) else "failed"
    elif error_kind in {"unresolved_items", "page_limit", "duplicate_page"}:
        status = "partial"
    elif error_kind:
        status = "partial" if any(row["seller_id"] for row in rows) else "parse_failed"
    else:
        status = "ok"
    summary = _finish(conn, run_id, keyword, status, error_kind)
    if caught and not summary["unique_seller_count"]:
        raise caught
    return summary

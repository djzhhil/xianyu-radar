"""Paged seller discovery with resumable work and redacted diagnostics."""

from __future__ import annotations

import sqlite3

from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.goofish.errors import STOP_KINDS
from xianyu_radar.modules.discovery.keyword_search import search
from xianyu_radar.modules.discovery.pagination import following_page
from xianyu_radar.modules.discovery.diagnostics import error_kind_for
from xianyu_radar.modules.discovery.enrichment import enrich_pending
from xianyu_radar.modules.discovery import repository


def list_discovery_runs(conn: sqlite3.Connection, *, limit: int = 20, offset: int = 0) -> dict:
    return repository.list_discovery_runs(conn, limit=limit, offset=offset)


def get_discovery_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    return repository.get_discovery_run(conn, run_id)


def discover_sellers(
    conn: sqlite3.Connection, keyword: str, *, session: Session,
    enrich: bool = True, max_enrich: int = 30, max_pages: int = 3,
    resume_run_id: str | None = None, rows_per_page: int = 30,
) -> dict:
    """Search bounded pages, persist each page, and resume pending detail work."""
    if not 1 <= max_pages <= 50 or rows_per_page < 1 or max_enrich < 0:
        raise ValueError("invalid discovery limits")
    run_id, page = repository.start_run(conn, keyword, max_pages, resume_run_id)
    error_kind = None
    caught: Exception | None = None
    while page and page <= max_pages:
        try:
            found = search(keyword, session) if page == 1 else search(keyword, session, page_number=page)
            raw_count = getattr(found, "raw_count", len(found))
            following, page_error = following_page(found, page, rows_per_page)
            added = repository.save_page(
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
            repository.set_next_page(conn, run_id, page)
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
    repository.mark_unresolved(conn, run_id, enrich=enrich, error_kind=error_kind)
    rows, unparsed = repository.resolution_summary(conn, run_id)
    unresolved = sum(not row["seller_id"] for row in rows)
    if error_kind is None and unparsed:
        error_kind = "parse_failed"
    if error_kind is None and any(row["error_kind"] == "network" for row in rows):
        error_kind = "network"
    if error_kind is None and unresolved:
        error_kind = "unresolved_items"
    if error_kind in STOP_KINDS:
        status = error_kind
    elif error_kind == "network":
        status = "partial" if any(row["seller_id"] for row in rows) else "failed"
    elif error_kind in {"unresolved_items", "page_limit", "duplicate_page"}:
        status = "partial"
    elif error_kind:
        status = "partial" if any(row["seller_id"] for row in rows) else "parse_failed"
    else:
        status = "ok"
    summary = repository.finish_run(conn, run_id, keyword, status, error_kind)
    if caught and not summary["unique_seller_count"]:
        raise caught
    return summary

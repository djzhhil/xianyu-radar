"""Enrich seed items with seller_id and upsert into seller pool."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from xianyu_radar.auth.mtop import MtopError, call_mtop
from xianyu_radar.auth.session import Session
from xianyu_radar.discovery.item_parser import extract_seller_id, extract_seller_nick
from xianyu_radar.discovery.keyword_search import search, search_from_fixture
from xianyu_radar.models import SeedItem
from xianyu_radar.sellers.pool import add_seller_from_discovery, upsert_seed_item


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_detail(session: Session, item_id: str) -> dict:
    return call_mtop(
        session,
        "taobao.idle.pc.detail",
        {
            "id": str(item_id),
            "returnItemDO": True,
            "needSellerDO": True,
        },
        {"spm_cnt": "a21ybx.item.0.0"},
    )


def enrich_seller_id(session: Session, item: SeedItem) -> SeedItem:
    if item.seller_id:
        return item
    try:
        detail = fetch_detail(session, item.item_id)
    except (MtopError, Exception):
        return item
    sid = extract_seller_id(detail)
    nick = extract_seller_nick(detail)
    if sid:
        item.seller_id = sid
    if nick and not item.seller_nick:
        item.seller_nick = nick
    return item


def discover_sellers(
    conn: sqlite3.Connection,
    keyword: str,
    *,
    session: Session | None = None,
    fixture_path: str | None = None,
    enrich: bool = True,
    max_enrich: int = 30,
) -> dict:
    """
    Search keyword → optional detail enrich → write items + seller pool.
    Returns summary dict.
    """
    run_id = f"disc_{uuid.uuid4().hex[:12]}"
    started = _now()
    conn.execute(
        "INSERT INTO discovery_runs(id, keyword, started_at, status) VALUES (?,?,?,?)",
        (run_id, keyword, started, "running"),
    )
    conn.commit()

    if fixture_path:
        items = search_from_fixture(fixture_path)
    else:
        if session is None:
            raise ValueError("session required for online discover")
        items = search(keyword, session)

    enriched = 0
    skipped_no_seller = 0
    new_sellers = 0

    if enrich and session is not None:
        for item in items[:max_enrich]:
            if item.seller_id:
                continue
            before = item.seller_id
            enrich_seller_id(session, item)
            if item.seller_id and item.seller_id != before:
                enriched += 1

    # Ensure keyword registered
    conn.execute(
        "INSERT OR IGNORE INTO watch_keywords(keyword, exclude_patterns, enabled, created_at) "
        "VALUES (?, NULL, 1, ?)",
        (keyword, _now()),
    )

    for item in items:
        upsert_seed_item(conn, item, keyword=keyword)
        if not item.seller_id:
            skipped_no_seller += 1
            continue
        created = add_seller_from_discovery(
            conn,
            seller_id=item.seller_id,
            nickname=item.seller_nick,
            source_keyword=keyword,
            source_item_id=item.item_id,
        )
        if created:
            new_sellers += 1

    conn.execute(
        "UPDATE discovery_runs SET finished_at=?, item_count=?, seller_count=?, status=? WHERE id=?",
        (_now(), len(items), new_sellers, "ok", run_id),
    )
    conn.commit()
    return {
        "run_id": run_id,
        "keyword": keyword,
        "item_count": len(items),
        "enriched": enriched,
        "skipped_no_seller": skipped_no_seller,
        "new_sellers": new_sellers,
        "items": items,
    }

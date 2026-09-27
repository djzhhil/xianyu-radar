"""Enrich seed items with seller_id and upsert into seller pool."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from xianyu_radar.infrastructure.goofish.mtop import MtopError, call_mtop
from xianyu_radar.infrastructure.goofish.session import AuthError, Session
from xianyu_radar.modules.discovery.item_parser import extract_seller_id, extract_seller_nick
from xianyu_radar.modules.discovery.keyword_search import search
from xianyu_radar.models import SeedItem
from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery, upsert_seed_item

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_user_validation_error(exc: MtopError) -> bool:
    return "FAIL_SYS_USER_VALIDATE" in str(exc.ret) or "x5sec" in str(exc).lower()


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
    except MtopError as exc:
        if _is_user_validation_error(exc):
            raise
        logger.warning("无法补全商品 %s 的卖家 ID：%s", item.item_id, exc)
        return item
    except AuthError:
        raise
    except Exception:
        logger.exception("补全商品 %s 的卖家 ID 时发生异常", item.item_id)
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
    session: Session,
    enrich: bool = True,
    max_enrich: int = 30,
) -> dict:
    """
    Search keyword → parse seller IDs → optional detail enrich → pool.
    Returns summary dict.
    """
    run_id = f"disc_{uuid.uuid4().hex[:12]}"
    started = _now()
    conn.execute(
        "INSERT INTO discovery_runs(id, keyword, started_at, status) VALUES (?,?,?,?)",
        (run_id, keyword, started, "running"),
    )
    conn.commit()

    enriched = 0
    validation_required = False
    skipped_no_seller = 0
    new_sellers = 0

    try:
        items = search(keyword, session)
        if enrich:
            selected = items[:max_enrich]
            for item in selected:
                if item.seller_id:
                    continue
                try:
                    enrich_seller_id(session, item)
                except MtopError as exc:
                    if not _is_user_validation_error(exc) or not any(
                        candidate.seller_id for candidate in selected
                    ):
                        raise
                    validation_required = True
                    break
                if item.seller_id:
                    enriched += 1
    except Exception:
        conn.execute(
            "UPDATE discovery_runs SET finished_at=?, status='failed' WHERE id=?",
            (_now(), run_id),
        )
        conn.commit()
        raise

    # Ensure keyword registered
    conn.execute(
        "INSERT OR IGNORE INTO watch_keywords(keyword, exclude_patterns, enabled, created_at) "
        "VALUES (?, NULL, 1, ?)",
        (keyword, _now()),
    )

    for item in items:
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
        upsert_seed_item(conn, item, keyword=keyword)

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
        "validation_required": validation_required,
        "skipped_no_seller": skipped_no_seller,
        "new_sellers": new_sellers,
        "items": items,
    }

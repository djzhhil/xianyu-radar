"""Enrich seed items with seller_id and upsert into seller pool."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from xianyu_radar.auth.mtop import MtopError, call_mtop
from xianyu_radar.auth.session import AuthError, Session
from xianyu_radar.discovery.item_parser import extract_seller_id, extract_seller_nick
from xianyu_radar.discovery.keyword_search import search, search_from_fixture
from xianyu_radar.models import SeedItem
from xianyu_radar.scheduler.runner import is_auth_paused
from xianyu_radar.sellers.pool import add_seller_from_discovery, upsert_seed_item


class DiscoveryRiskError(MtopError):
    """Raised when discovery hits VALIDATE / RGV587 and must stop."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _set_auth_paused(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused', '1')")
    conn.commit()


def _is_risk_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if isinstance(exc, AuthError):
        return True
    if isinstance(exc, MtopError):
        ret = exc.ret
        joined = " ".join(str(x) for x in ret) if isinstance(ret, list) else str(ret or "")
        u = (joined + " " + str(exc)).upper()
        if "VALIDATE" in u or "X5SEC" in u or "RGV587" in u or "挤爆" in str(exc):
            return True
        if "SESSION" in u or "TOKEN" in u:
            return True
    return "validate" in msg or "rgv587" in msg or "x5sec" in msg


def fetch_detail(session: Session, item_id: str) -> dict:
    """Call mtop.taobao.idle.pc.detail with official itemId payload + item Referer."""
    item_id = str(item_id)
    referer = f"https://www.goofish.com/item?id={item_id}"
    return call_mtop(
        session,
        "taobao.idle.pc.detail",
        {"itemId": item_id},
        {"spm_cnt": "a21ybx.item.0.0"},
        headers_extra={"Referer": referer},
    )


def enrich_seller_id(session: Session, item: SeedItem) -> SeedItem:
    """
    Fill seller_id from detail API.
    Soft failures (network/biz) leave item unchanged.
    Risk/auth failures re-raise so discover can pause.
    """
    if item.seller_id:
        return item
    try:
        detail = fetch_detail(session, item.item_id)
    except AuthError:
        raise
    except MtopError as e:
        if _is_risk_error(e):
            raise DiscoveryRiskError(str(e), ret=e.ret, payload=e.payload) from e
        return item
    except Exception:
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
    enrich: bool = False,
    max_enrich: int = 0,
) -> dict:
    """
    Search keyword → write items + seller pool.
    Seller ids preferably come from search CDN URLs; optional detail enrich is high-risk.
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
        if is_auth_paused(conn):
            conn.execute(
                "UPDATE discovery_runs SET finished_at=?, item_count=0, seller_count=0, status=? WHERE id=?",
                (_now(), "auth_paused", run_id),
            )
            conn.commit()
            return {
                "run_id": run_id,
                "keyword": keyword,
                "item_count": 0,
                "enriched": 0,
                "skipped_no_seller": 0,
                "new_sellers": 0,
                "items": [],
                "status": "auth_paused",
                "error": "auth_paused",
            }
        try:
            items = search(keyword, session)
        except (AuthError, MtopError) as e:
            if _is_risk_error(e):
                _set_auth_paused(conn)
            status = "auth_risk" if _is_risk_error(e) else "error"
            conn.execute(
                "UPDATE discovery_runs SET finished_at=?, item_count=0, seller_count=0, status=? WHERE id=?",
                (_now(), status, run_id),
            )
            conn.commit()
            raise

    enriched = 0
    skipped_no_seller = 0
    new_sellers = 0
    enrich_stopped_reason: str | None = None

    if enrich and session is not None:
        for item in items[:max_enrich]:
            if item.seller_id:
                continue
            before = item.seller_id
            try:
                enrich_seller_id(session, item)
            except (DiscoveryRiskError, AuthError) as e:
                enrich_stopped_reason = str(e)
                _set_auth_paused(conn)
                break
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

    status = "ok"
    if enrich_stopped_reason:
        status = "auth_risk"
    elif new_sellers == 0 and len(items) > 0 and enrich:
        status = "ok_no_sellers"

    conn.execute(
        "UPDATE discovery_runs SET finished_at=?, item_count=?, seller_count=?, status=? WHERE id=?",
        (_now(), len(items), new_sellers, status, run_id),
    )
    conn.commit()
    out = {
        "run_id": run_id,
        "keyword": keyword,
        "item_count": len(items),
        "enriched": enriched,
        "skipped_no_seller": skipped_no_seller,
        "new_sellers": new_sellers,
        "items": items,
        "status": status,
    }
    if enrich_stopped_reason:
        out["error"] = enrich_stopped_reason
        out["auth_paused"] = True
    return out

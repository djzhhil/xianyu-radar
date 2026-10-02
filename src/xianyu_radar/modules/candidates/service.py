"""Public candidate feature operations."""

from __future__ import annotations

import sqlite3
from xianyu_radar.models import SellerItem
from xianyu_radar.infrastructure.storage.candidate_repository import add_candidate_source

from xianyu_radar.modules.candidates.repository import (
    count_candidates,
    list_candidates,
    set_candidate_status,
    summarize_candidates,
    list_sources,
)

ALLOWED_STATUSES = frozenset({"new", "watching", "testing", "validated", "rejected"})


def change_status(conn: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    if status not in ALLOWED_STATUSES:
        raise ValueError("invalid status")
    return set_candidate_status(conn, candidate_id, status)


def select_catalog(conn: sqlite3.Connection, seller_id: str, scan_id: str, item_ids: list[str]) -> dict:
    item_ids = list(dict.fromkeys(item_ids))
    if not item_ids or len(item_ids) > 100:
        raise ValueError("请选择 1–100 件商品")
    with conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        scan = conn.execute(
            "SELECT id,finish_reason FROM scans WHERE seller_id=? AND status='ok' ORDER BY rowid DESC LIMIT 1",
            (seller_id,),
        ).fetchone()
        if not scan or scan["id"] != scan_id or scan["finish_reason"] not in {"end_marker", "short_page", "total_count"}:
            raise ValueError("目录已更新或缺少完整性依据，请刷新并完成扫描后再选择")
        if not conn.execute("SELECT 1 FROM seller_pool_entries WHERE seller_id=? AND active=1", (seller_id,)).fetchone():
            raise ValueError("商家不在商家池")
        rows = []
        for item_id in item_ids:
            row = conn.execute(
                "SELECT p.*,i.url FROM item_snapshots p JOIN items i ON i.item_id=p.item_id AND i.seller_id=p.seller_id "
                "WHERE p.scan_id=? AND p.seller_id=? AND p.item_id=? ORDER BY p.id DESC LIMIT 1",
                (scan_id, seller_id, item_id),
            ).fetchone()
            if not row:
                raise ValueError(f"商品 {item_id} 不在该完整目录中，请刷新复核")
            rows.append(row)
        results = [add_candidate_source(
            conn, seller_id, SellerItem(row["item_id"], row["title"] or "", row["price"] or "", row["url"] or "", image=row["image"]),
            source_type="baseline_catalog", scan_id=scan_id, observed_at=row["captured_at"],
        ) for row in rows]
    return {"added": sum(result["added"] for result in results), "existing": sum(not result["added"] for result in results), "results": results}

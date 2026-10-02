"""Candidate detector tests."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.infrastructure.storage.candidate_repository import match_exclusions
from xianyu_radar.modules.candidates.service import list_candidates
from xianyu_radar.modules.scan.diff import diff_items
from xianyu_radar.models import SeedItem, SellerItem
from xianyu_radar.modules.scan.service import apply_scan_result
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.seller_repository import upsert_seed_item


def test_explicit_patterns_match() -> None:
    assert match_exclusions("全新Sony A7M4资料", ["Sony A7M4"]) == ["Sony A7M4"]
    assert match_exclusions("Nikon Z8 教程", ["Sony A7M4"]) == []


def test_candidates_skip_baseline_but_keep_discovery_keyword(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    seller = "sellerA"
    # baseline
    r1 = apply_scan_result(
        conn,
        seller,
        [
            SellerItem("1", "Sony A7M4 资料", "10", "https://x/1"),
            SellerItem("2", "其他资料包", "5", "https://x/2"),
        ],
        keyword_hints=["Sony A7M4"],
    )
    assert all(e.is_baseline for e in r1["events"] if e.event_type == "NEW_ITEM")
    assert list_candidates(conn) == []

    # second scan: new non-target + new target-like
    r2 = apply_scan_result(
        conn,
        seller,
        [
            SellerItem("1", "Sony A7M4 资料", "10", "https://x/1"),
            SellerItem("2", "其他资料包", "5", "https://x/2"),
            SellerItem("3", "Photoshop 教程", "8", "https://x/3"),
            SellerItem("4", "Sony A7M4 进阶", "9", "https://x/4"),
        ],
        keyword_hints=["Sony A7M4"],
    )
    new_events = [e for e in r2["events"] if e.event_type == "NEW_ITEM"]
    assert {e.item_id for e in new_events} == {"3", "4"}
    cands = list_candidates(conn)
    titles = {c["sample_title"] for c in cands}
    assert "Photoshop 教程" in titles
    assert "Sony A7M4 进阶" in titles
    assert r2["candidates"]["skipped_target"] == 0
    conn.close()


def test_discovery_seed_does_not_turn_first_shop_scan_into_new_candidates(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "seeded.sqlite3")
    upsert_seed_item(
        conn,
        SeedItem("seed", "搜索标题", "10", "https://x/seed", seller_id="sellerA"),
        keyword="搜索标题",
    )
    upsert_seed_item(
        conn,
        SeedItem("stale", "已不在店铺", "11", "https://x/stale", seller_id="sellerA"),
        keyword="搜索标题",
    )
    conn.commit()

    first = apply_scan_result(
        conn,
        "sellerA",
        [SellerItem("seed", "店铺标题", "12", "https://x/seed"),
         SellerItem("existing", "其他库存", "8", "https://x/existing")],
    )
    assert first["candidates"]["added"] == 0
    assert {e.item_id for e in first["events"]} == {"seed", "existing"}
    assert all(e.event_type == "NEW_ITEM" and e.is_baseline for e in first["events"])
    assert conn.execute("SELECT status FROM items WHERE item_id='stale'").fetchone()[0] == "unknown"

    second = apply_scan_result(
        conn,
        "sellerA",
        [SellerItem("seed", "店铺标题", "12", "https://x/seed"),
         SellerItem("existing", "其他库存", "8", "https://x/existing"),
         SellerItem("fresh", "新商品", "9", "https://x/fresh")],
    )
    assert second["candidates"]["added"] == 1
    assert {e.item_id for e in second["events"]} == {"fresh"}
    conn.close()

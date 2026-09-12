"""Candidate detector tests."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.candidates.detector import is_target_product, list_candidates, process_new_item_events
from xianyu_radar.items.diff import diff_items
from xianyu_radar.models import SellerItem
from xianyu_radar.sellers.monitor import apply_scan_result
from xianyu_radar.storage.db import init_db


def test_is_target_product() -> None:
    assert is_target_product("全新Sony A7M4资料", ["Sony A7M4"])
    assert not is_target_product("Nikon Z8 教程", ["Sony A7M4"])


def test_candidates_skip_baseline_and_keyword(tmp_path: Path) -> None:
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
    assert not any("Sony A7M4 进阶" in t for t in titles)
    conn.close()

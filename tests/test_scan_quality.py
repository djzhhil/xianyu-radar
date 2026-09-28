"""Scan quality gates preserve the last trusted catalog."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.models import SellerItem
from xianyu_radar.modules.scan.models import SellerCatalog
from xianyu_radar.modules.scan.locks import seller_scan_lock
from xianyu_radar.modules.scan.service import apply_scan_result, scan_seller


def _items(count: int) -> list[SellerItem]:
    return [SellerItem(str(i), f"商品{i}", "10", f"https://x/{i}") for i in range(count)]


def test_incomplete_scan_does_not_change_current_items(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "incomplete.sqlite3")
    apply_scan_result(conn, "seller", _items(3))
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items",
        lambda *_: SellerCatalog(_items(1), 3, 1, "end_marker", False),
    )
    result = scan_seller(conn, Session("cookie", "token", "test"), "seller")
    assert result["status"] == "failed"
    assert result["error_kind"] == "incomplete"
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM item_events").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
    conn.close()


def test_large_drop_requires_matching_complete_rescan(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "drop.sqlite3")
    apply_scan_result(conn, "seller", _items(70))
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items",
        lambda *_: SellerCatalog(_items(8), 8, 1, "total_count", True),
    )
    session = Session("cookie", "token", "test")
    first = scan_seller(conn, session, "seller")
    assert first["status"] == "suspect"
    assert first["events"] == []
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0] == 70

    second = scan_seller(conn, session, "seller")
    assert second["status"] == "ok"
    assert len([e for e in second["events"] if e.event_type == "REMOVED_ITEM"]) == 62
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status='removed'").fetchone()[0] == 62
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
    conn.close()


def test_normal_removal_requires_two_complete_scans(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "removal.sqlite3")
    apply_scan_result(conn, "seller", _items(2))
    first = apply_scan_result(conn, "seller", _items(1))
    assert not any(e.event_type == "REMOVED_ITEM" for e in first["events"])
    assert conn.execute("SELECT missing_count FROM items WHERE item_id='1'").fetchone()[0] == 1
    second = apply_scan_result(conn, "seller", _items(1))
    assert [e.item_id for e in second["events"] if e.event_type == "REMOVED_ITEM"] == ["1"]
    assert conn.execute("SELECT status FROM items WHERE item_id='1'").fetchone()[0] == "removed"
    conn.close()


def test_same_seller_scan_lock_is_exclusive() -> None:
    with seller_scan_lock("seller") as first:
        assert first
        with seller_scan_lock("seller") as second:
            assert not second
        with seller_scan_lock("other") as different_seller:
            assert different_seller


def test_verified_empty_shop_requires_two_complete_observations(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "empty.sqlite3")
    apply_scan_result(conn, "seller", _items(25))
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items",
        lambda *_: SellerCatalog([], 0, 1, "empty_catalog", True),
    )
    session = Session("cookie", "token", "test")
    first = scan_seller(conn, session, "seller")
    assert first["status"] == "suspect"
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0] == 25

    second = scan_seller(conn, session, "seller")
    assert second["status"] == "ok"
    assert len([e for e in second["events"] if e.event_type == "REMOVED_ITEM"]) == 25
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status='removed'").fetchone()[0] == 25
    third = scan_seller(conn, session, "seller")
    assert third["status"] == "ok"
    assert third["events"] == []
    conn.close()

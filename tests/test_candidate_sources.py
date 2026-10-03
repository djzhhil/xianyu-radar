"""Provenance, deduplication and legacy preservation for candidates."""

from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.models import SellerItem
from xianyu_radar.modules.scan.service import apply_scan_result
from xianyu_radar.modules.candidates.service import list_sources, list_candidates
from xianyu_radar.infrastructure.storage.candidate_repository import add_candidate_source
from xianyu_radar.modules.candidates.service import select_catalog
from xianyu_radar.modules.pool.service import add_seller
from xianyu_radar.modules.scan.models import SellerCatalog
from xianyu_radar.infrastructure.storage.seller_repository import get_pool_seller_detail
import pytest


@pytest.mark.parametrize("status,reason,trusted", [
    ("ok", "end_marker", True), ("ok", "short_page", True),
    ("ok", "total_count", True), ("ok", "duplicate_page", False),
    ("ok", None, False), ("failed", "end_marker", False),
    ("suspect", "total_count", False),
])
def test_catalog_and_candidate_selection_agree_on_scan_quality(tmp_path, status, reason, trusted):
    conn = init_db(tmp_path / "quality.sqlite3")
    add_seller(conn, "12345")
    items = [SellerItem("1", "商品", "10", "")]
    apply_scan_result(conn, "12345", items, scan_id="scan")
    conn.execute("UPDATE scans SET status=?,finish_reason=? WHERE id='scan'", (status, reason))
    conn.commit()
    detail = get_pool_seller_detail(conn, "12345")
    assert detail["items"][0]["selectable"] is trusted
    assert detail["selection_scan_id"] == ("scan" if trusted else None)
    if trusted:
        assert select_catalog(conn, "12345", "scan", ["1"])["added"] == 1
    else:
        with pytest.raises(ValueError):
            select_catalog(conn, "12345", "scan", ["1"])
    conn.close()


def test_new_item_sources_keep_each_product_and_scan(tmp_path):
    conn = init_db(tmp_path / "sources.sqlite3")
    for seller in ["a", "b"]:
        base = SellerItem(f"base-{seller}", "库存", "1", "")
        apply_scan_result(conn, seller, [base], scan_id=f"base-{seller}")
        new = SellerItem(f"new-{seller}", "FDE 新资料", "10", f"https://www.goofish.com/item?id={seller}")
        apply_scan_result(conn, seller, [base, new], scan_id=f"new-{seller}")
    candidate = list_candidates(conn)[0]
    sources = list_sources(conn, candidate["candidate_id"], limit=1)
    assert candidate["seller_count"] == 2
    assert candidate["appearance_count"] == 2
    assert candidate["source_types"] == {"new_item": 2}
    assert sources["total"] == 2 and len(sources["sources"]) == 1
    assert sources["sources"][0]["scan_id"] == "new-b"
    assert sources["sources"][0]["price"] == "10"
    repeat = add_candidate_source(conn, "b", new, source_type="new_item", scan_id="new-b")
    assert not repeat["added"]
    assert list_candidates(conn)[0]["appearance_count"] == 2
    assert list_sources(conn, 999) is None
    conn.close()


def test_reliable_source_does_not_promote_legacy_quality_or_review(tmp_path):
    conn = init_db(tmp_path / "legacy.sqlite3")
    conn.execute("INSERT INTO candidates(normalized_title,first_seen_at,last_seen_at,status,quality_flag) VALUES ('fde','t','t','rejected','legacy_unverified')")
    apply_scan_result(conn, "a", [SellerItem("base", "库存", "1", "")])
    apply_scan_result(conn, "a", [SellerItem("base", "库存", "1", ""), SellerItem("new", "FDE", "10", "")])
    candidate = list_candidates(conn)[0]
    assert candidate["status"] == "rejected"
    assert candidate["quality_flag"] == "legacy_unverified"
    assert candidate["source_types"] == {"new_item": 1}
    conn.close()


def test_manual_catalog_selection_is_atomic_and_does_not_create_new_events(tmp_path):
    conn = init_db(tmp_path / "manual.sqlite3")
    add_seller(conn, "12345")
    items = [SellerItem("1", "FDE 存量", "10", "https://www.goofish.com/item?id=1")]
    apply_scan_result(conn, "12345", items, scan_id="baseline", catalog=SellerCatalog(items, 1, 1, "end_marker", True))
    before = conn.execute("SELECT COUNT(*) FROM item_events").fetchone()[0]
    with pytest.raises(ValueError):
        select_catalog(conn, "12345", "baseline", ["1", "missing"])
    assert list_candidates(conn) == []
    result = select_catalog(conn, "12345", "baseline", ["1", "1"])
    assert result["added"] == 1
    candidate = list_candidates(conn)[0]
    assert candidate["source_types"] == {"baseline_catalog": 1}
    assert select_catalog(conn, "12345", "baseline", ["1"])["existing"] == 1
    assert conn.execute("SELECT COUNT(*) FROM item_events").fetchone()[0] == before
    conn.execute("INSERT INTO scans(id,seller_id,started_at,status,error_kind) VALUES ('failure','12345','t','failed','incomplete')")
    conn.commit()
    assert select_catalog(conn, "12345", "baseline", ["1"])["existing"] == 1
    apply_scan_result(conn, "12345", items, scan_id="updated", catalog=SellerCatalog(items, 1, 1, "end_marker", True))
    with pytest.raises(ValueError):
        select_catalog(conn, "12345", "baseline", ["1"])
    conn.close()


def test_seed_only_or_old_scan_without_quality_evidence_cannot_be_selected(tmp_path):
    conn = init_db(tmp_path / "untrusted.sqlite3")
    add_seller(conn, "12345")
    with pytest.raises(ValueError):
        select_catalog(conn, "12345", "missing", ["1"])
    apply_scan_result(conn, "12345", [SellerItem("1", "旧目录", "10", "")], scan_id="old")
    with pytest.raises(ValueError):
        select_catalog(conn, "12345", "old", ["1"])
    assert list_candidates(conn) == []
    conn.close()

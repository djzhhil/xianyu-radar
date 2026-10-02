"""Provenance, deduplication and legacy preservation for candidates."""

from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.models import SellerItem
from xianyu_radar.modules.scan.service import apply_scan_result
from xianyu_radar.modules.candidates.service import list_sources, list_candidates
from xianyu_radar.infrastructure.storage.candidate_repository import add_candidate_source


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

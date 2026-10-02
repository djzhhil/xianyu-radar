"""Explicit exclusion rules never reinterpret discovery or manual selection."""

import pytest

from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.models import SellerItem
from xianyu_radar.modules.candidates.service import list_candidates, select_catalog
from xianyu_radar.modules.pool.service import add_seller, change_candidate_rules, preview_candidate_rules
from xianyu_radar.modules.scan.history import list_candidate_decisions
from xianyu_radar.modules.scan.models import SellerCatalog
from xianyu_radar.modules.scan.service import apply_scan_result


def test_rule_normalization_preview_and_validation(tmp_path):
    conn = init_db(tmp_path / "rules.sqlite3")
    add_seller(conn, "123")
    assert not change_candidate_rules(conn, "missing", ["FDE"])
    assert preview_candidate_rules(conn, "missing") is None
    assert change_candidate_rules(conn, "123", [" FDE ", "fde", "资料"])
    items = [SellerItem(str(i), "FDE 资料", "10", "") for i in range(3)]
    apply_scan_result(conn, "123", items, scan_id="base")
    preview = preview_candidate_rules(conn, "123", limit=1, offset=1)
    assert preview["exclude_patterns"] == ["FDE", "资料"]
    assert preview["total"] == 3
    assert preview["matches"] == [{"item_id": "1", "title": "FDE 资料", "matched_patterns": ["FDE", "资料"]}]
    for patterns in [["  "], ["!!"], ["x" * 81], [str(i) for i in range(21)]]:
        with pytest.raises(ValueError):
            change_candidate_rules(conn, "123", patterns)
    assert preview_candidate_rules(conn, "123")["exclude_patterns"] == ["FDE", "资料"]
    change_candidate_rules(conn, "123", [])
    assert preview_candidate_rules(conn, "123")["total"] == 0
    conn.close()


def test_scan_decisions_are_preserved_and_manual_selection_bypasses_rules(tmp_path):
    conn = init_db(tmp_path / "decisions.sqlite3")
    add_seller(conn, "123")
    change_candidate_rules(conn, "123", ["旧版"])
    base = SellerItem("base", "FDE 旧版库存", "10", "")
    apply_scan_result(conn, "123", [base], scan_id="base")
    assert list_candidate_decisions(conn, "base")["decisions"][0]["decision"] == "baseline"
    items = [base, SellerItem("excluded", "FDE 旧版", "10", ""), SellerItem("keep", "FDE 新版", "10", "")]
    result = apply_scan_result(conn, "123", items, scan_id="new", keyword_hints=["FDE"],
                               catalog=SellerCatalog(items, 3, 1, "end_marker", True))
    assert result["candidates"]["added"] == result["candidates"]["skipped_excluded"] == 1
    decisions = list_candidate_decisions(conn, "new", limit=1)
    assert decisions["total"] == 2
    assert decisions["decisions"][0]["decision"] == "excluded"
    assert decisions["decisions"][0]["matched_patterns"] == ["旧版"]
    assert list_candidate_decisions(conn, "new", limit=1, offset=1)["decisions"][0]["decision"] == "candidate"
    assert [row["sample_title"] for row in list_candidates(conn)] == ["FDE 新版"]
    select_catalog(conn, "123", "new", ["excluded"])
    assert len(list_candidates(conn)) == 2
    change_candidate_rules(conn, "123", [])
    assert list_candidate_decisions(conn, "new")["decisions"][0]["matched_patterns"] == ["旧版"]
    # Removing rules is not a retroactive candidate import.
    apply_scan_result(conn, "123", items, scan_id="unchanged")
    assert list_candidate_decisions(conn, "unchanged")["total"] == 0
    conn.close()

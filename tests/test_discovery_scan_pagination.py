"""Regression coverage for bounded discovery and unreliable catalog totals."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.entrypoints.api.routes.discover import get_discovery_run
from xianyu_radar.entrypoints.api.routes.scan import get_scan_run
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery
from xianyu_radar.infrastructure.storage.seller_repository import list_pool
from xianyu_radar.modules.discovery.service import discover_sellers
from xianyu_radar.modules.scan.service import scan_seller


def _entry(item_id: str, seller_id: str | None = None) -> dict:
    args = {"id": item_id}
    if seller_id:
        args["seller_id"] = seller_id
    return {"data": {"item": {"main": {"exContent": {"itemId": item_id, "title": f"商品{item_id}"},
                                      "clickParam": {"args": args}}}}}


def _search_page(*entries: dict, next_page=None) -> dict:
    return {"data": {"resultList": list(entries), "nextPage": next_page}}


def _card(number: int) -> dict:
    return {"cardData": {"id": str(number), "title": f"商品{number}",
                         "detailParams": {"itemId": str(number)}}}


def test_discovery_page_limit_resumes_without_repeating_pages(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "discovery.sqlite3")
    calls = []
    pages = {
        1: _search_page(_entry("1", "101"), _entry("2", "202"), next_page=2),
        2: _search_page(_entry("3", "303"), next_page=False),
    }

    def fake_search(_session, _api, data, *_args, **_kwargs):
        calls.append(data["pageNumber"])
        return pages[data["pageNumber"]]

    monkeypatch.setattr("xianyu_radar.modules.discovery.keyword_search.call_mtop", fake_search)
    session = Session("cookie", "token", "test")
    first = discover_sellers(conn, "camera", session=session, enrich=False,
                             max_pages=1, rows_per_page=2)
    assert first["status"] == "partial"
    assert first["error_kind"] == "page_limit"
    assert first["page_count"] == 1
    assert first["new_sellers"] == 2

    resumed = discover_sellers(conn, "camera", session=session, enrich=False,
                               max_pages=2, resume_run_id=first["run_id"], rows_per_page=2)
    assert resumed["status"] == "ok"
    assert resumed["page_count"] == 2
    assert resumed["raw_result_count"] == 3
    assert resumed["item_count"] == 3
    assert resumed["unique_seller_count"] == 3
    assert resumed["new_sellers"] == 3
    assert conn.execute("SELECT COUNT(*) FROM seller_pool_entries").fetchone()[0] == 3
    assert calls == [1, 2]
    diagnostic = get_discovery_run(first["run_id"], conn)
    assert [page["raw_count"] for page in diagnostic["pages"]] == [2, 1]
    assert all(entry["outcome"] == "parsed" for entry in diagnostic["entries"])
    assert all("cookie" not in str(item["diagnostic"]).lower() for item in diagnostic["items"])
    conn.close()


def test_discovery_validation_stops_requests_and_resumes_detail(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "validation.sqlite3")
    page = _search_page(_entry("1", "101"), _entry("2"), next_page=False)
    search_calls = []
    monkeypatch.setattr(
        "xianyu_radar.modules.discovery.keyword_search.call_mtop",
        lambda *_args, **_kwargs: (search_calls.append(1), page)[1],
    )
    detail_calls = []

    def blocked(*_args):
        detail_calls.append("blocked")
        raise MtopError("x5sec", ret=["FAIL_SYS_USER_VALIDATE"])

    monkeypatch.setattr("xianyu_radar.modules.discovery.enrichment.fetch_detail", blocked)
    session = Session("cookie", "token", "test")
    first = discover_sellers(conn, "camera", session=session)
    assert first["status"] == "verification_required"
    assert first["new_sellers"] == 1
    assert first["skipped_no_seller"] == 1
    assert len(detail_calls) == 1
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 1

    monkeypatch.setattr(
        "xianyu_radar.modules.discovery.enrichment.fetch_detail",
        lambda *_args: {"data": {"sellerDO": {"sellerId": "202", "nick": "seller"}}},
    )
    resumed = discover_sellers(conn, "camera", session=session, resume_run_id=first["run_id"])
    assert resumed["status"] == "ok"
    assert resumed["new_sellers"] == 2
    assert resumed["skipped_no_seller"] == 0
    assert len(search_calls) == 1
    assert [row["resolution"] for row in get_discovery_run(first["run_id"], conn)["items"]] == ["search", "detail"]
    conn.close()


def test_unparsed_search_entry_cannot_be_reported_as_success(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "unparsed.sqlite3")
    page = _search_page(_entry("1", "101"), {"data": {"item": {"main": {}}}},
                        next_page=False)
    monkeypatch.setattr("xianyu_radar.modules.discovery.keyword_search.call_mtop",
                        lambda *_args, **_kwargs: page)
    result = discover_sellers(conn, "camera", session=Session("cookie", "token", "test"),
                              enrich=False)
    assert result["status"] == "partial"
    assert result["error_kind"] == "parse_failed"
    assert result["raw_result_count"] == 2
    assert result["item_count"] == 1
    assert result["unparsed_count"] == 1
    assert [entry["outcome"] for entry in get_discovery_run(result["run_id"], conn)["entries"]] == [
        "parsed", "missing_item_id",
    ]
    conn.close()


def test_conflicting_seller_on_later_page_revokes_earlier_pool_source(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "conflict.sqlite3")
    pages = [
        _search_page(_entry("1", "101"), next_page=2),
        _search_page(_entry("1", "202"), next_page=False),
    ]
    monkeypatch.setattr("xianyu_radar.modules.discovery.keyword_search.call_mtop",
                        lambda *_args, **_kwargs: pages.pop(0))
    session = Session("cookie", "token", "test")
    first = discover_sellers(conn, "camera", session=session, enrich=False, max_pages=1)
    assert [row["seller_id"] for row in list_pool(conn)] == ["101"]
    resumed = discover_sellers(conn, "camera", session=session, enrich=False,
                               max_pages=2, resume_run_id=first["run_id"])
    assert resumed["unique_seller_count"] == 0
    assert list_pool(conn) == []
    assert conn.execute("SELECT status FROM items WHERE item_id='1'").fetchone()[0] == "unknown"
    conn.close()


def test_rate_limit_on_later_search_page_stops_detail_requests(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "rate.sqlite3")
    calls = []

    def search_response(_session, _api, data, *_args, **_kwargs):
        calls.append(data["pageNumber"])
        if data["pageNumber"] == 2:
            raise MtopError("RGV587", ret=["RGV587"])
        return _search_page(_entry("1", "101"), _entry("2"), next_page=2)

    monkeypatch.setattr("xianyu_radar.modules.discovery.keyword_search.call_mtop", search_response)
    monkeypatch.setattr("xianyu_radar.modules.discovery.enrichment.fetch_detail",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("detail called after rate limit")))
    result = discover_sellers(conn, "camera", session=Session("cookie", "token", "test"))
    assert result["status"] == "rate_limit"
    assert result["page_count"] == 1
    assert result["next_page"] == 2
    assert result["new_sellers"] == 1
    assert calls == [1, 2]
    assert conn.execute("SELECT error_kind FROM discovery_items WHERE item_id='2'").fetchone()[0] == "rate_limit"
    conn.close()


def test_image_candidate_reused_across_pages_is_removed_from_pool(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "image-conflict.sqlite3")
    first = _entry("1", "opaque-a")
    second = _entry("2", "opaque-b")
    for entry in (first, second):
        entry["data"]["item"]["main"]["exContent"]["picUrl"] = (
            "https://img.alicdn.com/bao/uploaded/i1/2215811796357/example.jpg"
        )
    pages = [_search_page(first, next_page=2), _search_page(second, next_page=False)]
    monkeypatch.setattr("xianyu_radar.modules.discovery.keyword_search.call_mtop",
                        lambda *_args, **_kwargs: pages.pop(0))
    session = Session("cookie", "token", "test")
    initial = discover_sellers(conn, "camera", session=session, enrich=False, max_pages=1)
    assert len(list_pool(conn)) == 1
    resumed = discover_sellers(conn, "camera", session=session, enrich=False,
                               max_pages=2, resume_run_id=initial["run_id"])
    assert resumed["unique_seller_count"] == 0
    assert list_pool(conn) == []
    assert [row[0] for row in conn.execute(
        "SELECT error_kind FROM discovery_items ORDER BY item_id"
    )] == ["ambiguous_image", "ambiguous_image"]
    conn.close()


def test_zero_total_catalog_scans_and_records_redacted_pages(tmp_path: Path, monkeypatch) -> None:
    conn = init_db(tmp_path / "scan.sqlite3")
    add_seller_from_discovery(conn, seller_id="101", nickname=None,
                              source_keyword="camera", source_item_id=None)
    conn.commit()
    pages = [
        {"data": {"totalCount": 0, "nextPage": True,
                  "cardList": [_card(i) for i in range(20)]}},
        {"data": {"totalCount": 0, "nextPage": False,
                  "cardList": [_card(20), _card(21)]}},
    ]
    monkeypatch.setattr("xianyu_radar.modules.scan.fetcher.call_mtop",
                        lambda *_args, **_kwargs: pages.pop(0))
    session = Session("cookie", "token", "test")
    result = scan_seller(conn, session, "101")
    assert result["status"] == "ok"
    assert result["item_count"] == 22
    assert result["page_count"] == 2
    assert result["expected_count"] is None
    diagnostic = get_scan_run(result["scan_id"], conn)
    assert [page["card_count"] for page in diagnostic["pages"]] == [20, 2]
    assert [page["next_field"] for page in diagnostic["pages"]] == ["nextPage", "nextPage"]
    assert [page["unique_count"] for page in diagnostic["pages"]] == [20, 22]

    pages.extend([
        {"data": {"totalCount": 0, "nextPage": True,
                  "cardList": [_card(i) for i in range(20)]}},
        {"data": {"totalCount": 0, "cardList": []}},
    ])
    before = conn.execute("SELECT COUNT(*) FROM item_events").fetchone()[0]
    incomplete = scan_seller(conn, session, "101")
    assert incomplete["status"] == "failed"
    assert incomplete["finish_reason"] == "empty_page"
    assert conn.execute("SELECT COUNT(*) FROM item_events").fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0] == 22
    conn.close()

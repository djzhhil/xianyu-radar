"""Fetcher pagination with mock transport."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.modules.scan.fetcher import get_seller_items, get_seller_items_from_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _card(number: int) -> dict:
    return {"cardData": {"id": str(number), "title": f"商品{number}",
                         "detailParams": {"itemId": str(number)}}}


def test_parse_fixture() -> None:
    payload = json.loads((FIXTURES / "shop_items.json").read_text(encoding="utf-8"))
    items = get_seller_items_from_payload(payload)
    assert items
    assert len({i.item_id for i in items}) == len(items)


def test_pagination_merges_pages() -> None:
    page1 = {
        "ret": ["SUCCESS::调用成功"],
        "data": {
            "totalCount": 3,
            "nextPage": 2,
            "cardList": [
                {"cardData": {"id": "1", "title": "a", "priceInfo": {"price": "1"}, "detailParams": {"itemId": "1"}}},
                {"cardData": {"id": "2", "title": "b", "priceInfo": {"price": "2"}, "detailParams": {"itemId": "2"}}},
            ],
        },
    }
    page2 = {
        "ret": ["SUCCESS::调用成功"],
        "data": {
            "totalCount": 3,
            "nextPage": False,
            "cardList": [
                {"cardData": {"id": "3", "title": "c", "priceInfo": {"price": "3"}, "detailParams": {"itemId": "3"}}},
            ],
        },
    }
    session = Session(cookies="x=1", token="tok", source="test", cookie_count=1)
    with patch("xianyu_radar.modules.scan.fetcher.call_mtop", side_effect=[page1, page2]):
        catalog = get_seller_items(session, "999", page_size=2)
    assert catalog.complete
    assert catalog.page_count == 2
    assert [i.item_id for i in catalog.items] == ["1", "2", "3"]


def test_incomplete_catalog_reports_missing_items() -> None:
    payload = {
        "data": {
            "totalCount": 3,
            "nextPage": False,
            "cardList": [
                {"cardData": {"id": "1", "title": "a", "detailParams": {"itemId": "1"}}}
            ],
        }
    }
    session = Session(cookies="x=1", token="tok", source="test")
    with patch("xianyu_radar.modules.scan.fetcher.call_mtop", return_value=payload):
        catalog = get_seller_items(session, "999")
    assert not catalog.complete
    assert catalog.expected_count == 3
    assert len(catalog.items) == 1


def test_max_pages_without_terminal_signal_is_incomplete() -> None:
    payload = {
        "data": {
            "cardList": [
                {"cardData": {"id": "1", "title": "a", "detailParams": {"itemId": "1"}}}
            ],
        }
    }
    session = Session(cookies="x=1", token="tok", source="test")
    with patch("xianyu_radar.modules.scan.fetcher.call_mtop", return_value=payload):
        catalog = get_seller_items(session, "999", page_size=1, max_pages=1)
    assert not catalog.complete
    assert catalog.finish_reason == "max_pages"


def test_zero_total_with_full_page_follows_next_page_and_short_page() -> None:
    first = {"data": {"totalCount": 0, "nextPage": 2,
                      "cardList": [_card(i) for i in range(20)]}}
    second = {"data": {"totalCount": "0", "nextPage": False,
                       "cardList": [_card(20), _card(21)]}}
    session = Session("cookie", "token", "test")
    with patch("xianyu_radar.modules.scan.fetcher.call_mtop", side_effect=[first, second]) as call:
        catalog = get_seller_items(session, "999")
    assert call.call_count == 2
    assert catalog.complete
    assert catalog.expected_count is None
    assert catalog.finish_reason == "end_marker"
    assert len(catalog.items) == 22
    assert [page["unique_count"] for page in catalog.diagnostics] == [20, 22]
    assert catalog.diagnostics[0]["total_type"] == "int"
    assert catalog.diagnostics[1]["total_value"] == "0"


def test_zero_total_followed_by_ambiguous_empty_page_is_incomplete() -> None:
    first = {"data": {"totalCount": 0, "nextPage": True,
                      "cardList": [_card(i) for i in range(20)]}}
    second = {"data": {"totalCount": 0, "cardList": []}}
    session = Session("cookie", "token", "test")
    with patch("xianyu_radar.modules.scan.fetcher.call_mtop", side_effect=[first, second]):
        catalog = get_seller_items(session, "999")
    assert not catalog.complete
    assert catalog.finish_reason == "empty_page"
    assert catalog.expected_count is None
    assert len(catalog.items) == 20

"""Fetcher pagination with mock transport."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from xianyu_radar.auth.session import Session
from xianyu_radar.sellers.fetcher import get_seller_items, get_seller_items_from_payload

FIXTURES = Path(__file__).parent / "fixtures"


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
    with patch("xianyu_radar.sellers.fetcher.call_mtop", side_effect=[page1, page2]):
        items = get_seller_items(session, "999", page_size=2)
    assert [i.item_id for i in items] == ["1", "2", "3"]

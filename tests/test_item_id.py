"""Item id / search / shop parse tests."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.discovery.item_parser import (
    extract_item_id,
    extract_seller_id,
    parse_search_results,
    parse_shop_card_list,
)
from xianyu_radar.discovery.keyword_search import search_from_fixture

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_item_id_from_url() -> None:
    assert extract_item_id("https://www.goofish.com/item?id=123&foo=1") == "123"
    assert extract_item_id("fleamarket://item?id=456") == "456"
    assert extract_item_id("fleamarket://awesome_detail?itemId=789") == "789"


def test_parse_search_fixture() -> None:
    items = search_from_fixture(FIXTURES / "search_results.json")
    assert len(items) == 1
    assert items[0].item_id == "123456"
    assert "Sony" in items[0].title
    assert items[0].price


def test_parse_shop_fixture() -> None:
    import json

    payload = json.loads((FIXTURES / "shop_items.json").read_text(encoding="utf-8"))
    items = parse_shop_card_list(payload)
    assert len(items) >= 1
    assert all(i.item_id.isdigit() for i in items)


def test_extract_seller_id_from_detail() -> None:
    import json

    payload = json.loads((FIXTURES / "item_detail.json").read_text(encoding="utf-8"))
    assert extract_seller_id(payload) == "999888777"

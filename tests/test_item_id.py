"""Item id / search / shop parse tests."""

from __future__ import annotations

import json
from pathlib import Path

from xianyu_radar.modules.discovery.item_parser import extract_seller_id
from xianyu_radar.modules.discovery.keyword_search import search_from_payload
from xianyu_radar.infrastructure.item_identity import extract_item_id
from xianyu_radar.modules.scan.shop_parser import parse_shop_card_list

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_item_id_from_url() -> None:
    assert extract_item_id("https://www.goofish.com/item?id=123&foo=1") == "123"
    assert extract_item_id("fleamarket://item?id=456") == "456"
    assert extract_item_id("fleamarket://awesome_detail?itemId=789") == "789"


def test_parse_search_fixture() -> None:
    payload = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    items = search_from_payload(payload)
    assert len(items) == 1
    assert items[0].item_id == "123456"
    assert "Sony" in items[0].title
    assert items[0].price


def test_parse_search_seller_ids_only_when_numeric() -> None:
    payload = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    main = payload["data"]["resultList"][0]["data"]["item"]["main"]
    args = main["clickParam"]["args"]
    args["seller_id"] = "UFC_obfuscated_seller_id"
    main["exContent"]["jump2XianYuHao"] = {
        "clickParam": {"args": {"user_id": "Hz2_obfuscated_user_id"}}
    }
    assert search_from_payload(payload)[0].seller_id is None

    main["exContent"]["jump2XianYuHao"]["clickParam"]["args"]["user_id"] = "998877"
    assert search_from_payload(payload)[0].seller_id == "998877"

    args["seller_id"] = "112233"
    assert search_from_payload(payload)[0].seller_id == "112233"


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

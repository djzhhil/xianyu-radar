"""Tests for CDN seller-id extraction from search cards."""

from __future__ import annotations

from xianyu_radar.discovery.item_parser import (
    extract_seller_id_from_media,
    parse_search_results,
)


def test_extract_seller_from_alicdn_path():
    url = (
        "http://img.alicdn.com/bao/uploaded/i1/2226021703/"
        "O1CN014XCOfe1OS1dbRGkQP_!!4611686018427381063-0-xy_item.jpg"
    )
    assert extract_seller_id_from_media(url) == "2226021703"


def test_parse_search_uses_pic_url_seller():
    payload = {
        "data": {
            "resultList": [
                {
                    "data": {
                        "item": {
                            "main": {
                                "clickParam": {
                                    "args": {
                                        "id": "1051151784435",
                                        "seller_id": "lvL4zebblA8+SwLrXrJGHg==",
                                    }
                                },
                                "exContent": {
                                    "itemId": "1051151784435",
                                    "title": "教材",
                                    "userNickName": "云端知藏馆",
                                    "picUrl": (
                                        "http://img.alicdn.com/bao/uploaded/i1/2226021703/"
                                        "O1CN014XCOfe1OS1dbRGkQP_!!4611686018427381063-0-xy_item.jpg"
                                    ),
                                    "price": [{"text": "1"}],
                                },
                            }
                        }
                    }
                }
            ]
        }
    }
    items = parse_search_results(payload)
    assert len(items) == 1
    assert items[0].seller_id == "2226021703"
    assert items[0].seller_nick == "云端知藏馆"

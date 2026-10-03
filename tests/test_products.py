"""Product-only detail parsing and API errors."""

import pytest
from contextlib import contextmanager
from fastapi import HTTPException

from xianyu_radar.entrypoints.api.routes import products
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import AuthError, Session
from xianyu_radar.modules.products import service


def test_detail_preserves_zero_and_unknown_and_excludes_seller(monkeypatch):
    calls = []

    def response(session, api, data, params):
        calls.append((api, data))
        return {"data": {"itemDO": {
            "itemId": "123", "title": "商品", "soldPrice": 0,
            "gmtCreate": 1791000000000, "browseCnt": "1234", "wantCnt": 0,
            "interactFavorCnt": "7", "evaluateCnt": "2",
            "imageInfos": [{"url": "https://img.alicdn.com/example.jpg"}],
        }, "sellerDO": {"sellerId": "456", "nick": "seller"}}}

    monkeypatch.setattr(service, "call_mtop", response)
    result = service.get_detail(Session("cookie", "token", "test"), "123")
    assert calls == [("taobao.idle.pc.detail", {"id": "123", "returnItemDO": True, "needSellerDO": False})]
    assert result == {
        "item_id": "123", "title": "商品", "price": "0", "published_at": 1791000000000,
        "image": "https://img.alicdn.com/example.jpg", "views": 1234, "wants": 0,
        "favorites": None, "interactions": 7, "evaluations": 2,
    }


@pytest.mark.parametrize("payload", [{}, {"data": {}}, {"data": {"itemDO": []}},
                                     {"data": {"itemDO": {"itemId": "999"}}}])
def test_unusable_detail_is_rejected(payload):
    with pytest.raises(MtopError):
        service.parse_detail(payload, "123")


@pytest.mark.parametrize("value", [None, True, -1, "-1", "NaN", "1.5"])
def test_invalid_count_is_unknown(value):
    result = service.parse_detail({"data": {"itemDO": {"itemId": "123", "browseCnt": value}}}, "123")
    assert result["views"] is None


@pytest.mark.parametrize("item_id", ["0", "abc", "-1", "1" * 33])
def test_api_rejects_invalid_ids_before_loading_session(monkeypatch, item_id):
    monkeypatch.setattr(products, "require_session", lambda: pytest.fail("session should not be loaded"))
    with pytest.raises(HTTPException) as error:
        products.product_detail(item_id)
    assert error.value.status_code == 400


@pytest.mark.parametrize("exception,status", [
    (MtopError("x5sec / USER_VALIDATE required"), 403),
    (MtopError("RGV587"), 429), (MtopError("invalid response"), 502),
    (AuthError("token expired"), 401),
])
def test_api_reports_platform_errors(monkeypatch, exception, status):
    @contextmanager
    def operation():
        try:
            yield Session("synthetic", "fixture", "offline")
        except Exception:
            raise
    monkeypatch.setattr("xianyu_radar.entrypoints.api.deps.session_operation", operation)

    def fail(*args):
        raise exception

    monkeypatch.setattr(products, "get_detail", fail)
    with pytest.raises(HTTPException) as error:
        products.product_detail("123")
    assert error.value.status_code == status


def test_api_requires_helper_config(monkeypatch):
    for key in ("BASE_URL", "USERNAME", "PASSWORD", "ACCOUNT_ID"):
        monkeypatch.delenv("RADAR_HELPER_" + key, raising=False)
    with pytest.raises(HTTPException) as error:
        products.product_detail("123")
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "helper_config"

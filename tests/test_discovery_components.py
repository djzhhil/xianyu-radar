"""Focused coverage for discovery's internal components."""

import json

import pytest

from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.modules.discovery.diagnostics import detail_diagnostic, error_kind_for

from xianyu_radar.modules.discovery.pagination import following_page


class Page(list):
    pass


@pytest.mark.parametrize("signal, expected", [
    (False, (0, None)), ("false", (0, None)), (0, (0, None)),
    (True, (2, None)), ("true", (2, None)), (3, (3, None)),
    ("4", (4, None)), (1, (1, "invalid_next_page")),
    ("invalid", (1, "invalid_next_page")),
])
def test_explicit_next_page(signal, expected):
    found = Page()
    found.next_page = signal
    assert following_page(found, 1, 30) == expected


@pytest.mark.parametrize("raw_count, expected", [(30, (2, None)), (29, (0, None))])
def test_next_page_falls_back_to_raw_count(raw_count, expected):
    found = Page()
    found.raw_count = raw_count
    assert following_page(found, 1, 30) == expected


def test_next_page_uses_has_next_when_next_page_missing():
    found = Page()
    found.has_next = True
    assert following_page(found, 2, 30) == (3, None)


@pytest.mark.parametrize("error, expected", [
    (AuthError("expired"), "auth"),
    (MtopError("x5sec", ret=["FAIL_SYS_USER_VALIDATE"]), "verification_required"),
    (MtopError("RGV587", ret=[]), "rate_limit"),
    (MtopError("timeout", ret=[]), "network"),
    (ValueError("invalid"), "parse_failed"),
])
def test_discovery_error_classification(error, expected):
    assert error_kind_for(error) == expected


def test_detail_diagnostic_keeps_field_names_not_values():
    detail = {"data": {"sellerDO": {"sellerId": "123", "nick": "private-name", "bad/key": "secret"}}}
    assert json.loads(detail_diagnostic(detail, "123")) == {
        "source": "sellerDO", "detail_fields": ["nick", "sellerId"],
    }
    assert json.loads(detail_diagnostic({"data": []}, None)) == {
        "source": "unresolved", "detail_fields": [],
    }

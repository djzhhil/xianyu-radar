"""Focused coverage for discovery's internal components."""

import pytest

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

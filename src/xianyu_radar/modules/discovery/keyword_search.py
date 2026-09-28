"""Keyword search via MTOP."""

from __future__ import annotations

from typing import Any

from xianyu_radar.infrastructure.goofish.mtop import call_mtop
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.modules.discovery.item_parser import parse_search_results
from xianyu_radar.models import SeedItem


class DiscoveryParseError(Exception):
    """The search API returned an unusable success payload."""


class SearchPage(list[SeedItem]):
    def __init__(self, items: list[SeedItem], payload: dict[str, Any]):
        super().__init__(items)
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise DiscoveryParseError("search data is not an object")
        entries = data.get("resultList")
        if not isinstance(entries, list):
            raise DiscoveryParseError("search resultList is missing or not a list")
        self.entries = entries
        self.raw_count = len(self.entries)
        self.result_type = type(entries).__name__
        self.next_page = data.get("nextPage")
        if self.next_page is None:
            self.next_page = data.get("nextPageNum")
        self.has_next = data.get("hasNext")


def search_from_payload(payload: dict[str, Any]) -> list[SeedItem]:
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("resultList"), list):
        raise DiscoveryParseError("search resultList is missing or not a list")
    return parse_search_results(payload)


def search(
    keyword: str,
    session: Session,
    *,
    page_number: int = 1,
    rows_per_page: int = 30,
) -> SearchPage:
    """Online keyword search. Requires valid session."""
    payload = call_mtop(
        session,
        "taobao.idlemtopsearch.pc.search",
        {
            "pageNumber": page_number,
            "keyword": keyword,
            "fromFilter": False,
            "rowsPerPage": rows_per_page,
            "sortValue": "",
            "sortField": "",
            "customDistance": "",
            "gps": "",
            "propValueStr": {},
            "customGps": "",
            "searchReqFromPage": "pcSearch",
            "extraFilterValue": "{}",
            "userPositionJson": "{}",
        },
        {"spm_cnt": "a21ybx.search.0.0"},
    )
    return SearchPage(search_from_payload(payload), payload)

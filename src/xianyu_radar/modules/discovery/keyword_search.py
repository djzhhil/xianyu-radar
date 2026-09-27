"""Keyword search via MTOP."""

from __future__ import annotations

from typing import Any

from xianyu_radar.infrastructure.goofish.mtop import call_mtop
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.modules.discovery.item_parser import parse_search_results
from xianyu_radar.models import SeedItem


def search_from_payload(payload: dict[str, Any]) -> list[SeedItem]:
    return parse_search_results(payload)


def search(
    keyword: str,
    session: Session,
    *,
    page_number: int = 1,
    rows_per_page: int = 30,
) -> list[SeedItem]:
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
    return search_from_payload(payload)

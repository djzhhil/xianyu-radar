"""Fetch all on-sale items for a seller via MTOP list API."""

from __future__ import annotations

from typing import Any

from xianyu_radar.infrastructure.goofish.mtop import call_mtop
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.modules.scan.shop_parser import parse_shop_card_list
from xianyu_radar.modules.scan.models import SellerCatalog
from xianyu_radar.models import SellerItem


def get_seller_items_from_payload(payload: dict[str, Any]) -> list[SellerItem]:
    return parse_shop_card_list(payload)


def get_seller_items(
    session: Session,
    seller_id: str,
    *,
    page_size: int = 20,
    max_pages: int = 50,
) -> SellerCatalog:
    """Paginate idle.web.xyh.item.list and report whether the catalog is complete."""
    all_items: list[SellerItem] = []
    seen: set[str] = set()
    page = 1
    total_count: int | None = None
    page_count = 0
    visited_pages: set[int] = set()

    def result(reason: str, complete: bool) -> SellerCatalog:
        return SellerCatalog(all_items, total_count, page_count, reason, complete)

    while page <= max_pages:
        if page in visited_pages:
            return result("page_loop", False)
        visited_pages.add(page)
        payload = call_mtop(
            session,
            "idle.web.xyh.item.list",
            {
                "needGroupInfo": True,
                "pageNumber": page,
                "userId": str(seller_id),
                "pageSize": page_size,
            },
            {"spm_cnt": "a21ybx.personal.0.0"},
        )
        page_count += 1
        data = payload.get("data") or {}
        raw_total = data.get("totalCount")
        if raw_total is not None:
            try:
                reported_total = int(raw_total)
            except (TypeError, ValueError):
                return result("invalid_total_count", False)
            if reported_total < 0 or (total_count is not None and reported_total != total_count):
                return result("changing_total_count", False)
            total_count = reported_total

        raw_cards = data.get("cardList") or []
        if not isinstance(raw_cards, list):
            return result("invalid_card_list", False)
        batch = parse_shop_card_list(payload)
        if len(batch) != len(raw_cards):
            return result("unparsed_cards", False)
        if not batch:
            return result("empty_catalog", total_count == 0 and page_count == 1)
        new = 0
        for it in batch:
            if it.item_id in seen:
                continue
            seen.add(it.item_id)
            all_items.append(it)
            new += 1
        if new == 0:
            return result("duplicate_page", False)
        if new != len(batch):
            return result("duplicate_items", False)
        if total_count is not None and len(all_items) > total_count:
            return result("more_than_total", False)

        if total_count is not None and len(all_items) == total_count:
            return result("total_count", True)

        next_page = data.get("nextPage")
        if next_page is None:
            next_page = data.get("nextPageNum")
        explicit_end = next_page in (False, "false", 0, "0")
        if explicit_end or (next_page is None and len(batch) < page_size):
            complete = total_count is None or len(all_items) == total_count
            return result("end_marker" if explicit_end else "short_page", complete)

        if next_page is None or next_page is True or str(next_page).lower() == "true":
            page += 1
        elif str(next_page).isdigit():
            following = int(next_page)
            if following <= page:
                return result("page_loop", False)
            page = following
        else:
            return result("invalid_next_page", False)

    return result("max_pages", False)

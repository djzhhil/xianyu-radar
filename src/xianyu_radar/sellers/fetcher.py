"""Fetch all on-sale items for a seller via MTOP list API."""

from __future__ import annotations

from typing import Any

from xianyu_radar.auth.mtop import call_mtop
from xianyu_radar.auth.session import Session
from xianyu_radar.discovery.item_parser import parse_shop_card_list
from xianyu_radar.models import SellerItem


def get_seller_items_from_payload(payload: dict[str, Any]) -> list[SellerItem]:
    return parse_shop_card_list(payload)


def get_seller_items(
    session: Session,
    seller_id: str,
    *,
    page_size: int = 20,
    max_pages: int = 50,
) -> list[SellerItem]:
    """Paginate idle.web.xyh.item.list until exhausted."""
    all_items: list[SellerItem] = []
    seen: set[str] = set()
    page = 1
    total_count: int | None = None

    while page <= max_pages:
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
        data = payload.get("data") or {}
        if total_count is None:
            try:
                total_count = int(data.get("totalCount") or 0)
            except (TypeError, ValueError):
                total_count = 0

        batch = parse_shop_card_list(payload)
        if not batch:
            break
        new = 0
        for it in batch:
            if it.item_id in seen:
                continue
            seen.add(it.item_id)
            all_items.append(it)
            new += 1
        if new == 0:
            break

        # Pagination signals
        next_page = data.get("nextPage") or data.get("nextPageNum")
        if next_page in (False, "false", 0, "0", None):
            if total_count and len(all_items) >= total_count:
                break
            if len(batch) < page_size:
                break
            # if nextPage absent but more expected, continue
            if total_count and len(all_items) < total_count:
                page += 1
                continue
            break
        page = int(next_page) if str(next_page).isdigit() else page + 1

        if total_count and len(all_items) >= total_count:
            break

    return all_items

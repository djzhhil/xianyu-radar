"""Fetch all on-sale items for a seller via MTOP list API."""

from __future__ import annotations

from typing import Any, Callable

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
    on_page: Callable[[dict], None] | None = None,
) -> SellerCatalog:
    """Paginate idle.web.xyh.item.list and report whether the catalog is complete."""
    all_items: list[SellerItem] = []
    seen: set[str] = set()
    page = 1
    total_count: int | None = None
    page_count = 0
    visited_pages: set[int] = set()
    diagnostics: list[dict] = []
    group_params: dict[str, Any] = {}
    cursor: dict[str, Any] = {}

    def result(reason: str, complete: bool) -> SellerCatalog:
        return SellerCatalog(all_items, total_count, page_count, reason, complete, diagnostics)

    while page <= max_pages:
        if page in visited_pages:
            return result("page_loop", False)
        visited_pages.add(page)
        payload = call_mtop(
            session,
            "idle.web.xyh.item.list",
            {
                "needGroupInfo": not bool(group_params),
                "pageNumber": page,
                "userId": str(seller_id),
                "pageSize": page_size,
                **group_params,
                **cursor,
            },
            {"spm_cnt": "a21ybx.personal.0.0"},
        )
        page_count += 1
        data = payload.get("data") or {}
        if not group_params:
            groups = data.get("itemGroupList") or []
            for group in groups if isinstance(groups, list) else []:
                if not isinstance(group, dict):
                    continue
                sorts = group.get("groupSortList") or []
                newest = next((sort for sort in sorts if isinstance(sort, dict)
                               and sort.get("groupSortId") == "newest"), None)
                if newest and group.get("groupId") is not None:
                    group_params = {"groupId": group["groupId"],
                                    "groupName": newest.get("groupSortName") or "最新",
                                    "defaultGroup": bool(group.get("defaultGroup")),
                                    "groupSortId": "newest"}
                    # The initial recommendation page is not a complete inventory page.
                    visited_pages.remove(page)
                    page_count -= 1
                    break
            if group_params:
                continue
        raw_total = data.get("totalCount")
        total_error = None
        if raw_total is not None:
            try:
                if isinstance(raw_total, bool) or not isinstance(raw_total, (int, str)):
                    raise ValueError("totalCount must be an integer")
                reported_total = int(raw_total)
            except (TypeError, ValueError):
                total_error = "invalid_total_count"
            else:
                if reported_total < 0 or (reported_total > 0 and total_count is not None and reported_total != total_count):
                    total_error = "changing_total_count"
                elif reported_total > 0:
                    total_count = reported_total

        raw_cards = data.get("cardList") or []
        cards_valid = isinstance(raw_cards, list)
        parsed_batch = parse_shop_card_list(payload) if cards_valid else []
        batch = [item for item in parsed_batch if item.raw_status != "1"]
        new = 0
        for it in batch:
            if it.item_id in seen:
                continue
            seen.add(it.item_id)
            all_items.append(it)
            new += 1
        next_field = "nextPage" if data.get("nextPage") is not None else None
        next_page = data.get("nextPage")
        if next_page is None:
            next_field = "nextPageNum" if data.get("nextPageNum") is not None else None
            next_page = data.get("nextPageNum")
        explicit_end = next_page in (False, "false", 0, "0")
        diagnostic = {
            "page_number": page,
            "total_type": type(raw_total).__name__,
            "total_value": str(raw_total) if isinstance(raw_total, int) and not isinstance(raw_total, bool) or (isinstance(raw_total, str) and raw_total.isdigit()) else None,
            "card_count": len(raw_cards) if cards_valid else 0,
            "parsed_count": len(parsed_batch),
            "next_field": next_field,
            "next_page": str(next_page) if isinstance(next_page, (bool, int)) or (isinstance(next_page, str) and (next_page.isdigit() or next_page.lower() in {"true", "false"})) else None,
            "unique_count": len(all_items),
        }
        diagnostics.append(diagnostic)
        if on_page:
            on_page(diagnostic)
        if total_error:
            return result(total_error, False)
        if not cards_valid:
            return result("invalid_card_list", False)
        if len(parsed_batch) != len(raw_cards):
            return result("unparsed_cards", False)
        if not parsed_batch:
            if page_count == 1 and explicit_end and raw_total == 0:
                total_count = 0
                return result("empty_catalog", True)
            if page_count > 1 and explicit_end and all_items and total_count is None:
                return result("end_marker", True)
            return result("empty_page", False)
        if new == 0 and batch:
            return result("duplicate_page", False)
        if new != len(batch):
            return result("duplicate_items", False)
        if total_count is not None and len(all_items) > total_count:
            return result("more_than_total", False)

        if total_count is not None and len(all_items) == total_count:
            return result("total_count", True)

        if explicit_end or (next_page is None and len(parsed_batch) < page_size):
            complete = total_count is None or len(all_items) == total_count
            return result("end_marker" if explicit_end else "short_page", complete)

        model = data.get("nextPageModel")
        cursor_number = data.get("nextPageNum")
        if isinstance(model, str) and model and isinstance(cursor_number, (int, str)) and not isinstance(cursor_number, bool):
            cursor = {"nextPageModel": model, "nextPageNum": cursor_number}
            page += 1
        elif next_page is None or next_page is True or str(next_page).lower() == "true":
            page += 1
        elif str(next_page).isdigit():
            following = int(next_page)
            if following <= page:
                return result("page_loop", False)
            page = following
        else:
            return result("invalid_next_page", False)

    return result("max_pages", False)

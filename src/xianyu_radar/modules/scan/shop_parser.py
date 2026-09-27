"""Parse a seller's shop item-list response."""

from __future__ import annotations

from typing import Any

from xianyu_radar.models import SellerItem
from xianyu_radar.infrastructure.item_identity import extract_item_id, normalize_goofish_url


def parse_shop_card_list(payload: dict[str, Any]) -> list[SellerItem]:
    """Parse mtop.idle.web.xyh.item.list response."""
    data = payload.get("data") or {}
    cards = data.get("cardList") or []
    items: list[SellerItem] = []
    seen: set[str] = set()
    for card in cards:
        cd = card.get("cardData") or {}
        detail = cd.get("detailParams") or {}
        item_id = extract_item_id(
            detail.get("itemId"),
            cd.get("id"),
            cd.get("detailUrl"),
        )
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        title = cd.get("title") or detail.get("title") or ""
        price = ""
        price_info = cd.get("priceInfo") or {}
        if isinstance(price_info, dict):
            price = str(price_info.get("price") or price_info.get("soldPrice") or "")
        if not price:
            price = str(detail.get("soldPrice") or "")
        image = ""
        pic = cd.get("picInfo") or {}
        if isinstance(pic, dict):
            image = str(pic.get("url") or pic.get("picUrl") or "")
        if not image:
            image = str(detail.get("picUrl") or "")
        url = normalize_goofish_url(cd.get("detailUrl") or "", item_id)
        items.append(
            SellerItem(
                item_id=item_id,
                title=str(title).strip(),
                price=str(price).strip(),
                url=url,
                raw_status=str(cd.get("itemStatus") or ""),
                image=image,
            )
        )
    return items

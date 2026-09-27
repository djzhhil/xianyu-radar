"""Parse keyword search and item-detail responses for seller discovery."""

from __future__ import annotations

from typing import Any

from xianyu_radar.models import SeedItem
from xianyu_radar.infrastructure.item_identity import extract_item_id, normalize_goofish_url


def _price_from_ex_content(ex: dict) -> str:
    price_parts = ex.get("price") or []
    if isinstance(price_parts, list):
        price = "".join(
            str(p.get("text", "")) for p in price_parts if isinstance(p, dict)
        )
        return price.replace("当前价", "").replace("¥", "").replace("\u00a5", "").strip()
    return str(price_parts)


def parse_search_results(payload: dict[str, Any]) -> list[SeedItem]:
    """Parse mtop.taobao.idlemtopsearch.pc.search response (or fixture)."""
    result_list = (payload.get("data") or {}).get("resultList") or []
    items: list[SeedItem] = []
    for entry in result_list:
        main = (((entry.get("data") or {}).get("item") or {}).get("main") or {})
        ex = main.get("exContent") or {}
        args = ((main.get("clickParam") or {}).get("args") or {})

        item_id = extract_item_id(
            ex.get("itemId"),
            args.get("id"),
            args.get("item_id"),
            main.get("targetUrl"),
        )
        if not item_id:
            continue

        title = ex.get("title") or args.get("title") or ""
        if not title and isinstance(ex.get("richTitle"), list):
            title = "".join(
                (t.get("data") or {}).get("text", "")
                for t in ex["richTitle"]
                if isinstance(t, dict)
            )

        price = _price_from_ex_content(ex) or str(
            args.get("price") or args.get("displayPrice") or ""
        )
        raw_link = main.get("targetUrl") or ""
        url = normalize_goofish_url(raw_link, item_id)
        seller_nick = ex.get("userNickName") or None
        # Rare: userId in args
        seller_id = extract_item_id(args.get("userId"), args.get("sellerId"))
        # extract_item_id is for items; seller ids are also numeric strings
        for key in ("userId", "sellerId", "uid"):
            val = args.get(key)
            if val is not None and str(val).isdigit():
                seller_id = str(val)
                break

        items.append(
            SeedItem(
                item_id=item_id,
                title=str(title).strip(),
                price=str(price).strip(),
                url=url,
                seller_id=seller_id,
                seller_nick=seller_nick,
                raw=entry,
            )
        )
    return items


def extract_seller_id(detail_payload: dict[str, Any]) -> str | None:
    """From mtop.taobao.idle.pc.detail response."""
    data = detail_payload.get("data") or detail_payload
    seller = data.get("sellerDO") or {}
    sid = seller.get("sellerId") or seller.get("userId")
    if sid is None:
        return None
    s = str(sid).strip()
    return s if s.isdigit() else None


def extract_seller_nick(detail_payload: dict[str, Any]) -> str | None:
    data = detail_payload.get("data") or detail_payload
    seller = data.get("sellerDO") or {}
    nick = seller.get("nick") or seller.get("userNick")
    return str(nick) if nick else None

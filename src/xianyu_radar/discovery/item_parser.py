"""Parse search / shop / detail payloads into structured items."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from xianyu_radar.models import SeedItem, SellerItem

ITEM_ID_RE = re.compile(r"(?:(?:itemId|id)=)(\d+)", re.I)
FLEAMARKET_RE = re.compile(r"fleamarket://(?:item|awesome_detail).*?[?&](?:itemId|id)=(\d+)", re.I)
# Taobao/Xianyu CDN often embeds numeric userId: .../uploaded/i1/2226021703/O1CN0...
CDN_USER_ID_RE = re.compile(
    r"(?:alicdn\.com|taobaocdn\.com)/[^?]*/(?:uploaded/)?i\d+/(\d{5,16})/",
    re.I,
)


def extract_item_id(*candidates: Any) -> str | None:
    """Extract a stable item id from ids, URLs, or nested dict snippets."""
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            s = str(int(c))
            if s.isdigit():
                return s
        if isinstance(c, str):
            s = c.strip()
            if s.isdigit():
                return s
            m = ITEM_ID_RE.search(s) or FLEAMARKET_RE.search(s)
            if m:
                return m.group(1)
            # query string only
            if "id=" in s or "itemId=" in s:
                parsed = urlparse(s if "://" in s else f"https://x/?{s.lstrip('?')}")
                qs = parse_qs(parsed.query)
                for key in ("itemId", "id"):
                    if key in qs and qs[key]:
                        val = qs[key][0]
                        if str(val).isdigit():
                            return str(val)
        if isinstance(c, dict):
            for key in ("itemId", "item_id", "id"):
                if key in c:
                    got = extract_item_id(c[key])
                    if got:
                        return got
    return None


def extract_seller_id_from_media(*candidates: Any) -> str | None:
    """Extract numeric seller/user id from alicdn/taobaocdn image URLs."""
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, dict):
            for key in ("url", "picUrl", "userAvatarUrl", "pic"):
                if key in c:
                    got = extract_seller_id_from_media(c[key])
                    if got:
                        return got
            continue
        s = str(c).strip()
        if not s:
            continue
        m = CDN_USER_ID_RE.search(s)
        if m:
            return m.group(1)
    return None


def normalize_goofish_url(raw: str, item_id: str | None = None) -> str:
    if not raw and item_id:
        return f"https://www.goofish.com/item?id={item_id}"
    url = raw.replace("fleamarket://item", "https://www.goofish.com/item")
    url = url.replace("fleamarket://awesome_detail", "https://www.goofish.com/item")
    if url.startswith("fleamarket://"):
        url = "https://www.goofish.com/" + url.split("://", 1)[1]
    if item_id and "id=" not in url and "itemId=" not in url:
        return f"https://www.goofish.com/item?id={item_id}"
    # normalize itemId= to id=
    if "itemId=" in url and "id=" not in url:
        url = url.replace("itemId=", "id=")
    return url


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
        # Prefer plaintext numeric ids when present.
        seller_id = None
        for key in ("userId", "sellerId", "uid"):
            val = args.get(key)
            if val is not None and str(val).isdigit():
                seller_id = str(val)
                break
        # Search cards usually encrypt seller_id; recover from CDN image paths instead.
        if not seller_id:
            detail_params = ex.get("detailParams") or {}
            seller_id = extract_seller_id_from_media(
                ex.get("picUrl"),
                ex.get("userAvatarUrl"),
                detail_params.get("picUrl") if isinstance(detail_params, dict) else None,
                main.get("picUrl"),
            )

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


def extract_seller_id(detail_payload: dict[str, Any]) -> str | None:
    """From mtop.taobao.idle.pc.detail response (sellerDO / item nested shapes)."""
    data = detail_payload.get("data") or detail_payload
    if not isinstance(data, dict):
        return None
    candidates: list[Any] = []
    seller = data.get("sellerDO") or data.get("seller") or {}
    if isinstance(seller, dict):
        candidates.extend(
            [
                seller.get("sellerId"),
                seller.get("userId"),
                seller.get("uid"),
                seller.get("id"),
            ]
        )
    item = data.get("itemDO") or data.get("item") or {}
    if isinstance(item, dict):
        candidates.extend(
            [
                item.get("sellerId"),
                item.get("userId"),
                (item.get("seller") or {}).get("userId")
                if isinstance(item.get("seller"), dict)
                else None,
            ]
        )
    for key in ("sellerId", "userId", "uid"):
        candidates.append(data.get(key))
    for sid in candidates:
        if sid is None:
            continue
        s = str(sid).strip()
        if s.isdigit():
            return s
    return None


def extract_seller_nick(detail_payload: dict[str, Any]) -> str | None:
    data = detail_payload.get("data") or detail_payload
    if not isinstance(data, dict):
        return None
    seller = data.get("sellerDO") or data.get("seller") or {}
    if isinstance(seller, dict):
        nick = seller.get("nick") or seller.get("userNick") or seller.get("sellerNick")
        if nick:
            return str(nick)
    item = data.get("itemDO") or data.get("item") or {}
    if isinstance(item, dict):
        nick = item.get("userNick") or item.get("sellerNick")
        if nick:
            return str(nick)
    return None

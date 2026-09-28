"""Parse keyword search and item-detail responses for seller discovery."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

from xianyu_radar.models import SeedItem
from xianyu_radar.infrastructure.item_identity import extract_item_id, normalize_goofish_url


IMAGE_SELLER_PATH = re.compile(r"^/bao/uploaded/i[1-4]/([0-9]{9,16})/[^/]+$")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def image_seller_id_candidate(pic_url: Any) -> str | None:
    """Read a possible seller ID from an Alibaba uploaded-image path."""
    if not isinstance(pic_url, str):
        return None
    parsed = urlsplit(pic_url)
    if parsed.hostname != "img.alicdn.com":
        return None
    match = IMAGE_SELLER_PATH.fullmatch(parsed.path)
    return match.group(1) if match else None


def _price_from_ex_content(ex: dict) -> str:
    price_parts = ex.get("price") or []
    if isinstance(price_parts, list):
        price = "".join(
            str(p.get("text", "")) for p in price_parts if isinstance(p, dict)
        )
        return price.replace("当前价", "").replace("¥", "").replace("\u00a5", "").strip()
    return str(price_parts)


def _seller_id_candidates(args: dict, ex: dict) -> set[str]:
    """Collect numeric IDs from seller-specific fields only."""
    jump = _as_dict(ex.get("jump2XianYuHao"))
    jump_args = _as_dict(_as_dict(jump.get("clickParam")).get("args"))
    candidates = set()
    for source, keys in ((args, ("sellerId", "seller_id")),
                         (jump_args, ("sellerId", "seller_id", "userId"))):
        for key in keys:
            value = source.get(key)
            if value is not None:
                candidate = str(value).strip()
                if candidate.isascii() and candidate.isdigit():
                    candidates.add(candidate)
    return candidates


def _seller_id_from_search(args: dict, ex: dict) -> str | None:
    candidates = _seller_id_candidates(args, ex)
    return next(iter(candidates)) if len(candidates) == 1 else None


def parse_search_results(payload: dict[str, Any]) -> list[SeedItem]:
    """Parse mtop.taobao.idlemtopsearch.pc.search response."""
    result_list = (payload.get("data") or {}).get("resultList") or []
    items: list[SeedItem] = []
    image_groups: dict[tuple[str, str], list[tuple[SeedItem, str | None]]] = defaultdict(list)
    conflicting_items: set[str] = set()
    for entry in result_list:
        if not isinstance(entry, dict):
            continue
        entry_data = entry.get("data")
        item_data = entry_data.get("item") if isinstance(entry_data, dict) else None
        main = item_data.get("main") if isinstance(item_data, dict) else None
        if not isinstance(main, dict):
            continue
        ex = main.get("exContent") or {}
        args = _as_dict(_as_dict(main.get("clickParam")).get("args"))
        if not isinstance(ex, dict) or not isinstance(args, dict):
            continue

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
        seller_id = _seller_id_from_search(args, ex)
        if len(_seller_id_candidates(args, ex)) > 1:
            conflicting_items.add(item_id)
        jump_args = _as_dict(_as_dict(
            _as_dict(ex.get("jump2XianYuHao")).get("clickParam")
        ).get("args"))
        search_seller_ref = (
            args.get("seller_id") or args.get("sellerId") or jump_args.get("seller_id")
            or jump_args.get("sellerId") or jump_args.get("userId")
        )

        item = SeedItem(
            item_id=item_id,
            title=str(title).strip(),
            price=str(price).strip(),
            url=url,
            seller_id=seller_id,
            seller_nick=seller_nick,
            raw=entry,
        )
        items.append(item)
        group_key = (
            ("seller", str(search_seller_ref))
            if search_seller_ref
            else ("item", item_id)
        )
        image_groups[group_key].append((item, image_seller_id_candidate(ex.get("picUrl"))))

    # Resolve in memory only. Shared image uploaders and conflicting images are ambiguous.
    candidate_groups: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for group_key, group in image_groups.items():
        for _, candidate in group:
            if candidate:
                candidate_groups[candidate].add(group_key)
    for group_key, group in image_groups.items():
        if any(item.item_id in conflicting_items for item, _ in group):
            continue
        candidates = {candidate for _, candidate in group if candidate}
        explicit_ids = {item.seller_id for item, _ in group if item.seller_id}
        if len(candidates) != 1:
            continue
        candidate = next(iter(candidates))
        if len(candidate_groups[candidate]) != 1 or (explicit_ids and explicit_ids != {candidate}):
            continue
        for item, _ in group:
            if not item.seller_id and item.item_id not in conflicting_items:
                item.seller_id = candidate
    return items


def extract_seller_id(detail_payload: dict[str, Any]) -> str | None:
    """From mtop.taobao.idle.pc.detail response."""
    data = detail_payload.get("data") or detail_payload
    seller = data.get("sellerDO") or {}
    sid = seller.get("sellerId") or seller.get("userId")
    if sid is None:
        return None
    s = str(sid).strip()
    return s if s.isascii() and s.isdigit() else None


def extract_seller_nick(detail_payload: dict[str, Any]) -> str | None:
    data = detail_payload.get("data") or detail_payload
    seller = data.get("sellerDO") or {}
    nick = seller.get("nick") or seller.get("userNick")
    return str(nick) if nick else None

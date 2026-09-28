"""Diff current seller catalog vs previous DB state."""

from __future__ import annotations

from xianyu_radar.models import ItemEvent, SellerItem


def _norm(s: str | None) -> str:
    if s is None:
        return ""
    # NFKC-ish light normalize: strip + fullwidth spaces
    return str(s).replace("\u3000", " ").strip()


def diff_items(
    seller_id: str,
    previous: dict[str, dict],
    current: list[SellerItem],
    *,
    baseline: bool,
    allow_removed: bool = True,
    missing_increment: int = 1,
) -> list[ItemEvent]:
    """
    previous: item_id -> row dict with title, price, missing_count, status
    current: fresh fetch list

    A baseline is the first successful full shop scan, even when discovery seeds exist.
    If current is empty and allow_removed=False → no REMOVED (caller should skip).
    """
    events: list[ItemEvent] = []
    current_map = {i.item_id: i for i in current}
    if baseline:
        return [
            ItemEvent(
                item_id=item.item_id,
                seller_id=seller_id,
                event_type="NEW_ITEM",
                new_value=item.title,
                is_baseline=True,
            )
            for item in current_map.values()
        ]

    for item_id, item in current_map.items():
        if item_id not in previous:
            events.append(
                ItemEvent(
                    item_id=item_id,
                    seller_id=seller_id,
                    event_type="NEW_ITEM",
                    new_value=item.title,
                    is_baseline=False,
                )
            )
            continue
        prev = previous[item_id]
        old_title = _norm(prev.get("last_title") or prev.get("title"))
        new_title = _norm(item.title)
        old_price = _norm(prev.get("last_price") or prev.get("price"))
        new_price = _norm(item.price)
        if old_title != new_title:
            events.append(
                ItemEvent(
                    item_id=item_id,
                    seller_id=seller_id,
                    event_type="TITLE_CHANGED",
                    old_value=old_title,
                    new_value=new_title,
                )
            )
        if old_price != new_price and old_price and new_price:
            events.append(
                ItemEvent(
                    item_id=item_id,
                    seller_id=seller_id,
                    event_type="PRICE_CHANGED",
                    old_value=old_price,
                    new_value=new_price,
                )
            )

    if allow_removed:
        for item_id, prev in previous.items():
            if item_id in current_map:
                continue
            misses = int(prev.get("missing_count") or 0) + missing_increment
            if misses >= 2 and prev.get("status") == "active":
                events.append(
                    ItemEvent(
                        item_id=item_id,
                        seller_id=seller_id,
                        event_type="REMOVED_ITEM",
                        old_value=prev.get("title"),
                    )
                )

    return events

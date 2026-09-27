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
    allow_removed: bool = True,
) -> list[ItemEvent]:
    """
    previous: item_id -> row dict with title, price, check_count, status
    current: fresh fetch list

    If previous is empty → all NEW_ITEM with is_baseline=True.
    If current is empty and allow_removed=False → no REMOVED (caller should skip).
    """
    events: list[ItemEvent] = []
    current_map = {i.item_id: i for i in current}
    is_baseline = len(previous) == 0

    for item_id, item in current_map.items():
        if item_id not in previous:
            events.append(
                ItemEvent(
                    item_id=item_id,
                    seller_id=seller_id,
                    event_type="NEW_ITEM",
                    new_value=item.title,
                    is_baseline=is_baseline,
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

    if allow_removed and not is_baseline:
        for item_id, prev in previous.items():
            if item_id in current_map:
                continue
            check_count = int(prev.get("check_count") or 0)
            if check_count > 1 and prev.get("status") == "active":
                events.append(
                    ItemEvent(
                        item_id=item_id,
                        seller_id=seller_id,
                        event_type="REMOVED_ITEM",
                        old_value=prev.get("title"),
                    )
                )

    return events

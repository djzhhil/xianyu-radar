"""Candidate detection from trusted new-item events."""

from __future__ import annotations

import sqlite3

from xianyu_radar.infrastructure.storage.candidate_repository import add_candidate_source, normalize_title
from xianyu_radar.models import ItemEvent, SellerItem


def is_target_product(title: str, keyword_hints: list[str] | None) -> bool:
    if not keyword_hints:
        return False
    norm = normalize_title(title)
    return any(normalize_title(keyword) and normalize_title(keyword) in norm for keyword in keyword_hints)


def process_new_item_events(
    conn: sqlite3.Connection, events: list[ItemEvent], *,
    current_by_id: dict[str, SellerItem], keyword_hints: list[str] | None = None,
    scan_id: str | None = None,
) -> dict:
    added = skipped_baseline = skipped_target = 0
    for event in events:
        if event.event_type != "NEW_ITEM":
            continue
        if event.is_baseline:
            skipped_baseline += 1
            continue
        item = current_by_id.get(event.item_id) or SellerItem(event.item_id, event.new_value or "", "", "")
        if is_target_product(item.title, keyword_hints):
            skipped_target += 1
            continue
        result = add_candidate_source(conn, event.seller_id, item, source_type="new_item", scan_id=scan_id)
        added += int(result["added"])
    return {"added": added, "skipped_baseline": skipped_baseline, "skipped_target": skipped_target}

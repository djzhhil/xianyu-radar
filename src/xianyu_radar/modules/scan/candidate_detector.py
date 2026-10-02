"""Candidate detection from trusted new-item events."""

from __future__ import annotations

import sqlite3
import json

from xianyu_radar.infrastructure.storage.candidate_repository import add_candidate_source, match_exclusions
from xianyu_radar.models import ItemEvent, SellerItem


def process_new_item_events(
    conn: sqlite3.Connection, events: list[ItemEvent], *,
    current_by_id: dict[str, SellerItem], keyword_hints: list[str] | None = None,
    scan_id: str | None = None,
) -> dict:
    added = skipped_baseline = skipped_excluded = 0
    excluded = []
    for event in events:
        if event.event_type != "NEW_ITEM":
            continue
        item = current_by_id.get(event.item_id) or SellerItem(event.item_id, event.new_value or "", "", "")
        rules = conn.execute("SELECT candidate_exclude_patterns FROM sellers WHERE seller_id=?", (event.seller_id,)).fetchone()
        matched = match_exclusions(item.title, json.loads(rules[0]) if rules else [])
        decision = "baseline" if event.is_baseline else "excluded" if matched else "candidate"
        if scan_id:
            conn.execute(
                "INSERT INTO candidate_scan_decisions(scan_id,item_id,title,decision,matched_patterns) VALUES (?,?,?,?,?)",
                (scan_id, item.item_id, item.title, decision, json.dumps(matched, ensure_ascii=False)),
            )
        if event.is_baseline:
            skipped_baseline += 1
            continue
        if matched:
            skipped_excluded += 1
            excluded.append({"item_id": item.item_id, "title": item.title, "matched_patterns": matched})
            continue
        result = add_candidate_source(conn, event.seller_id, item, source_type="new_item", scan_id=scan_id)
        added += int(result["added"])
    return {"added": added, "skipped_baseline": skipped_baseline, "skipped_target": 0,
            "skipped_excluded": skipped_excluded, "excluded": excluded}

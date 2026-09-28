"""Diff engine table-driven tests."""

from __future__ import annotations

from xianyu_radar.modules.scan.diff import diff_items
from xianyu_radar.models import SellerItem


def _item(iid: str, title: str = "t", price: str = "1") -> SellerItem:
    return SellerItem(item_id=iid, title=title, price=price, url=f"https://x/{iid}")


def test_baseline_all_new() -> None:
    events = diff_items("s1", {}, [_item("1"), _item("2")], baseline=True)
    assert len(events) == 2
    assert all(e.event_type == "NEW_ITEM" and e.is_baseline for e in events)


def test_new_item() -> None:
    prev = {"1": {"title": "a", "price": "1", "check_count": 2, "status": "active"}}
    events = diff_items("s1", prev, [_item("1"), _item("2")], baseline=False)
    types = {e.event_type for e in events}
    assert "NEW_ITEM" in types
    assert not any(e.is_baseline for e in events if e.event_type == "NEW_ITEM")


def test_removed_requires_two_complete_absences() -> None:
    prev = {
        "1": {"title": "a", "price": "1", "missing_count": 0, "status": "active"},
        "2": {"title": "b", "price": "1", "missing_count": 1, "status": "active"},
    }
    events = diff_items("s1", prev, [_item("1")], baseline=False)
    removed = [e for e in events if e.event_type == "REMOVED_ITEM"]
    assert len(removed) == 1
    assert removed[0].item_id == "2"


def test_price_and_title_change() -> None:
    prev = {"1": {"title": "old", "price": "10", "check_count": 2, "status": "active",
                  "last_title": "old", "last_price": "10"}}
    events = diff_items("s1", prev, [_item("1", title="new", price="12")], baseline=False)
    types = {e.event_type for e in events}
    assert types == {"TITLE_CHANGED", "PRICE_CHANGED"}


def test_empty_current_no_removed_when_disallowed() -> None:
    prev = {"1": {"title": "a", "price": "1", "check_count": 5, "status": "active"}}
    events = diff_items("s1", prev, [], baseline=False, allow_removed=False)
    assert events == []


def test_baseline_ignores_discovery_seed() -> None:
    prev = {"1": {"title": "search title", "price": "10", "check_count": 0, "status": "active"}}
    events = diff_items("s1", prev, [_item("1", "shop title"), _item("2")], baseline=True)
    assert {e.item_id for e in events} == {"1", "2"}
    assert all(e.event_type == "NEW_ITEM" and e.is_baseline for e in events)

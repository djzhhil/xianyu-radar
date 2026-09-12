"""Shared models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SeedItem:
    item_id: str
    title: str
    price: str
    url: str
    seller_id: str | None = None
    seller_nick: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SellerItem:
    item_id: str
    title: str
    price: str
    url: str
    raw_status: str = ""
    image: str = ""


@dataclass
class ItemEvent:
    item_id: str
    seller_id: str
    event_type: str  # NEW_ITEM|REMOVED_ITEM|PRICE_CHANGED|TITLE_CHANGED
    old_value: str | None = None
    new_value: str | None = None
    is_baseline: bool = False

"""Models used only by the shop scanning workflow."""

from __future__ import annotations

from dataclasses import dataclass

from xianyu_radar.models import SellerItem


@dataclass
class SellerCatalog:
    items: list[SellerItem]
    expected_count: int | None
    page_count: int
    finish_reason: str
    complete: bool

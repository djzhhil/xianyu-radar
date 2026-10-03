"""Next-page rules for keyword discovery."""

from __future__ import annotations

from xianyu_radar.models import SeedItem


def following_page(found: list[SeedItem], page: int, rows_per_page: int) -> tuple[int, str | None]:
    signal = getattr(found, "next_page", None)
    if signal is None:
        signal = getattr(found, "has_next", None)
    if signal in (False, "false", 0, "0"):
        return 0, None
    if signal is True or str(signal).lower() == "true":
        return page + 1, None
    if signal is not None:
        if str(signal).isdigit() and int(signal) > page:
            return int(signal), None
        return page, "invalid_next_page"
    raw_count = getattr(found, "raw_count", len(found))
    return (page + 1, None) if raw_count >= rows_per_page else (0, None)

"""Shared eligibility rule for selecting a saved catalog."""


def is_trusted_scan(status: str | None, finish_reason: str | None) -> bool:
    return status == "ok" and finish_reason in {"end_marker", "short_page", "total_count"}

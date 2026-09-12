"""Clock helpers: persist and compare timestamps in Asia/Shanghai."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI)


def now_iso() -> str:
    """Wall-clock ISO timestamp in Asia/Shanghai, e.g. 2026-09-12T23:20:00+08:00."""
    return now_shanghai().replace(microsecond=0).isoformat()


def since_iso(delta: timedelta) -> str:
    """Cutoff timestamp (Shanghai) for ``now - delta`` range filters."""
    return (now_shanghai() - delta).replace(microsecond=0).isoformat()


def parse_relative_since(since: str | None) -> str | None:
    """Parse ``24h`` / ``7d`` into a Shanghai ISO cutoff; pass through other strings."""
    if not since:
        return None
    s = since.strip().lower()
    if s.endswith("h") and s[:-1].isdigit():
        return since_iso(timedelta(hours=int(s[:-1])))
    if s.endswith("d") and s[:-1].isdigit():
        return since_iso(timedelta(days=int(s[:-1])))
    return since


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

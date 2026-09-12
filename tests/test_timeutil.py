"""Tests for Asia/Shanghai clock helpers."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from xianyu_radar.timeutil import now_iso, now_shanghai, parse_relative_since, since_iso


def test_now_iso_is_shanghai_offset() -> None:
    s = now_iso()
    assert s.endswith("+08:00"), s
    assert len(s) >= 25
    # parseable and in Shanghai
    from datetime import datetime

    dt = datetime.fromisoformat(s)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=8)


def test_parse_relative_since_hours() -> None:
    cutoff = parse_relative_since("24h")
    assert cutoff is not None
    assert cutoff.endswith("+08:00")
    # roughly 24h before now
    from datetime import datetime

    parsed = datetime.fromisoformat(cutoff)
    delta = now_shanghai() - parsed.astimezone(ZoneInfo("Asia/Shanghai"))
    assert timedelta(hours=23, minutes=50) <= delta <= timedelta(hours=24, minutes=10)


def test_since_iso_days() -> None:
    s = since_iso(timedelta(days=7))
    assert s.endswith("+08:00")

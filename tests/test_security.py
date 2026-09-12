"""Tests for secret redaction and secret file permissions."""

from __future__ import annotations

import os
from pathlib import Path

from xianyu_radar.security import harden_path, is_world_readable, redact_secrets, write_secret_file


def test_redact_cookie_and_token():
    raw = (
        "Cookie: _m_h5_tk=abc_123; cookie2=secret; "
        "RADAR_BROKER_TOKEN=deadbeef "
        'Authorization: Bearer tok123 '
        '{"cookies":"a=1; b=2"}'
    )
    out = redact_secrets(raw)
    assert "abc_123" not in out
    assert "secret" not in out
    assert "deadbeef" not in out
    assert "tok123" not in out
    assert "***" in out


def test_write_secret_file_mode(tmp_path: Path):
    path = tmp_path / "state" / "default.json"
    write_secret_file(path, '{"cookie":"x=1"}\n')
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600
    assert not is_world_readable(path)
    harden_path(tmp_path / "state")
    assert (tmp_path / "state").stat().st_mode & 0o077 == 0

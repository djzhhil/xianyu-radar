"""MTOP sign unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xianyu_radar.auth.mtop import create_sign
from xianyu_radar.auth.session import AuthError, load_session


def test_create_sign_known_vector() -> None:
    # token&t&appKey&dataStr
    token = "abc"
    t = "1710000000000"
    data = json.dumps({"q": "test"}, ensure_ascii=False, separators=(",", ":"))
    assert create_sign(token, t, data) == "d41834f91639727f44a7e71f1b5f9946"


def test_load_session_from_cookie_header(tmp_path: Path) -> None:
    path = tmp_path / "default.json"
    path.write_text(
        json.dumps({"cookie": "a=1; _m_h5_tk=tokensecret_1710000000000; b=2"}),
        encoding="utf-8",
    )
    session = load_session(path)
    assert session.token == "tokensecret"
    assert "_m_h5_tk=" in session.cookies


def test_load_session_from_cookie_list(tmp_path: Path) -> None:
    path = tmp_path / "acc.json"
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "_m_h5_tk", "value": "hello_123"},
                    {"name": "cookie2", "value": "x"},
                ]
            }
        ),
        encoding="utf-8",
    )
    session = load_session(path)
    assert session.token == "hello"
    assert session.cookie_count == 2


def test_load_session_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AuthError):
        load_session(tmp_path / "nope.json")

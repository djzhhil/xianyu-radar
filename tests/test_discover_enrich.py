"""Unit tests for detail enrich payload and risk stop behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xianyu_radar.auth.mtop import MtopError
from xianyu_radar.auth.session import Session
from xianyu_radar.discovery.seller_discovery import (
    DiscoveryRiskError,
    discover_sellers,
    enrich_seller_id,
    fetch_detail,
)
from xianyu_radar.models import SeedItem
from xianyu_radar.storage.db import init_db


def test_fetch_detail_uses_item_id_payload():
    session = Session(cookies="_m_h5_tk=abc_1", token="abc", source="t", cookie_count=1)
    with patch("xianyu_radar.discovery.seller_discovery.call_mtop") as mock_call:
        mock_call.return_value = {"ret": ["SUCCESS"], "data": {"sellerDO": {"sellerId": "99"}}}
        fetch_detail(session, "12345")
        assert mock_call.call_args.args[1] == "taobao.idle.pc.detail"
        assert mock_call.call_args.args[2] == {"itemId": "12345"}


def test_enrich_raises_on_validate():
    session = Session(cookies="_m_h5_tk=abc_1", token="abc", source="t", cookie_count=1)
    item = SeedItem(item_id="1", title="t", price="1", url="u")
    with patch(
        "xianyu_radar.discovery.seller_discovery.fetch_detail",
        side_effect=MtopError("x5sec / USER_VALIDATE required", ret=["FAIL_SYS_USER_VALIDATE"]),
    ):
        with pytest.raises(DiscoveryRiskError):
            enrich_seller_id(session, item)


def test_discover_stops_enrich_and_pauses(tmp_path: Path):
    conn = init_db(tmp_path / "t.sqlite3")
    session = Session(cookies="_m_h5_tk=abc_1", token="abc", source="t", cookie_count=1)
    items = [
        SeedItem(item_id="1", title="a", price="1", url="u"),
        SeedItem(item_id="2", title="b", price="1", url="u"),
    ]

    def boom(sess, item):
        raise DiscoveryRiskError("VALIDATE", ret=["FAIL_SYS_USER_VALIDATE"])

    with patch("xianyu_radar.discovery.seller_discovery.search", return_value=items):
        with patch("xianyu_radar.discovery.seller_discovery.enrich_seller_id", side_effect=boom):
            summary = discover_sellers(conn, "kw", session=session, enrich=True, max_enrich=10)

    assert summary["status"] == "auth_risk"
    assert summary.get("auth_paused") is True
    row = conn.execute("SELECT value FROM meta WHERE key='auth_paused'").fetchone()
    assert row["value"] == "1"
    conn.close()

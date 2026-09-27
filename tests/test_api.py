"""API route behavior against an isolated database without a live HTTP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException
from pydantic import ValidationError

from xianyu_radar import config as cfg
from xianyu_radar.entrypoints.api.app import create_app
from xianyu_radar.entrypoints.api.routes import auth, candidates, discover, events, pool, scan, status
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery
from xianyu_radar.models import SellerItem
from xianyu_radar.modules.scan.fetcher import get_seller_items_from_payload

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cfg, "DEBUG_DIR", tmp_path / "debug")
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "radar.sqlite3")
    connection = init_db()
    try:
        yield connection
    finally:
        connection.close()


def test_app_has_one_data_environment() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/health" in paths
    assert "/api/discover" in paths
    assert "/api/env" not in paths
    assert "/api/demo/offline-loop" not in paths
    assert "fixture" not in discover.DiscoverBody.model_fields
    assert "fixture" not in scan.ScanSellerBody.model_fields
    with pytest.raises(ValidationError):
        discover.DiscoverBody(keyword="Sony A7M4", fixture="tests/fixtures/search_results.json")
    with pytest.raises(ValidationError):
        scan.ScanSellerBody(fixture="tests/fixtures/shop_items.json")
    assert status.health()["ok"] is True


def test_auth_and_discover_use_the_same_data_store(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    saved = auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=samplelongtoken_1710000000000; a=1"}),
        conn,
    )
    assert saved["ok"] is True
    assert auth.auth_status(conn)["looks_like_placeholder"] is False

    response = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    response["data"]["resultList"][0]["data"]["item"]["main"]["clickParam"]["args"]["seller_id"] = "998877"
    monkeypatch.setattr(
        "xianyu_radar.modules.discovery.keyword_search.call_mtop",
        lambda *args, **kwargs: response,
    )

    found = discover.discover(
        discover.DiscoverBody(keyword="Sony A7M4", no_enrich=True),
        conn,
    )
    assert found["item_count"] == 1
    assert found["new_sellers"] == 1
    assert status.status(conn)["counts"]["items"] == 1
    assert status.status(conn)["counts"]["watching_sellers"] == 1


def test_detail_validation_failure_is_visible_and_does_not_create_sellers(
    conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=samplelongtoken_1710000000000; a=1"}),
        conn,
    )
    response = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(
        "xianyu_radar.modules.discovery.keyword_search.call_mtop",
        lambda *args, **kwargs: response,
    )

    def blocked_detail(*args):
        raise MtopError("x5sec / USER_VALIDATE required", ret=["FAIL_SYS_USER_VALIDATE"])

    monkeypatch.setattr("xianyu_radar.modules.discovery.service.fetch_detail", blocked_detail)
    with pytest.raises(HTTPException) as error:
        discover.discover(discover.DiscoverBody(keyword="Sony A7M4"), conn)

    assert error.value.status_code == 403
    assert conn.execute("SELECT status FROM discovery_runs").fetchone()["status"] == "failed"
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def test_placeholder_cannot_be_scanned(conn) -> None:
    with pytest.raises(HTTPException) as error:
        scan.scan_one("unknown:123456", scan.ScanSellerBody(), conn)
    assert error.value.status_code == 400


def test_scan_candidates_and_events_share_the_same_data_store(
    conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=samplelongtoken_1710000000000; a=1"}),
        conn,
    )
    add_seller_from_discovery(
        conn, seller_id="SELLER_TEST", nickname="Example", source_keyword="Sony A7M4", source_item_id=None
    )
    conn.commit()
    assert pool.get_pool(conn=conn)["count"] == 1

    response = json.loads((FIXTURES / "shop_items.json").read_text(encoding="utf-8"))
    items = get_seller_items_from_payload(response)
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items", lambda *args: items
    )

    first = scan.scan_one(
        "SELLER_TEST",
        scan.ScanSellerBody(keyword="Sony A7M4"),
        conn,
    )
    assert first["status"] == "ok"
    new_item = SellerItem(
        item_id="999000111",
        title="Photoshop 完整教程",
        price="12",
        url="https://www.goofish.com/item?id=999000111",
    )
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items", lambda *args: items + [new_item]
    )
    second = scan.scan_one(
        "SELLER_TEST",
        scan.ScanSellerBody(keyword="Sony A7M4"),
        conn,
    )
    assert second["candidates"]["added"] >= 1
    listed = candidates.get_candidates(conn=conn)
    assert listed["count"] >= 1
    assert events.get_events(conn=conn)["count"] >= 1

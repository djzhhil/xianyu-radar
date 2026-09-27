"""Discover and pool integration with a simulated search response."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.modules.discovery.keyword_search import search_from_payload
from xianyu_radar.modules.discovery.service import discover_sellers
from xianyu_radar.infrastructure.storage.seller_repository import list_pool, upsert_seed_item
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.models import SeedItem

FIXTURES = Path(__file__).parent / "fixtures"


def test_discover_without_seller_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Search hits without a usable seller ID never become pool entries."""
    conn = init_db(tmp_path / "t.sqlite3")
    payload = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    items = search_from_payload(payload)
    monkeypatch.setattr("xianyu_radar.modules.discovery.service.search", lambda *args: items)
    summary = discover_sellers(
        conn,
        "Sony A7M4",
        session=Session(cookies="_m_h5_tk=sample_token", token="sample", source="test"),
        enrich=False,
    )
    assert summary["item_count"] == 1
    assert summary["skipped_no_seller"] == 1
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    assert list_pool(conn, status=None) == []
    conn.close()


def test_discover_numeric_seller_enters_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    payload = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    payload["data"]["resultList"][0]["data"]["item"]["main"]["clickParam"]["args"]["seller_id"] = "998877"
    items = search_from_payload(payload)
    monkeypatch.setattr("xianyu_radar.modules.discovery.service.search", lambda *args: items)
    session = Session(cookies="_m_h5_tk=sample_token", token="sample", source="test")

    first = discover_sellers(conn, "Sony A7M4", session=session, enrich=False)
    second = discover_sellers(conn, "Sony A7M4", session=session, enrich=False)

    assert first["new_sellers"] == 1
    assert second["new_sellers"] == 0
    assert first["skipped_no_seller"] == 0
    assert [row["seller_id"] for row in list_pool(conn)] == ["998877"]
    assert conn.execute("SELECT seller_id FROM items").fetchone()[0] == "998877"
    conn.close()


def test_legacy_placeholder_is_not_a_pool_seller(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    upsert_seed_item(
        conn,
        SeedItem(item_id="123456", title="Example", price="12", url="https://example.com"),
    )
    conn.commit()
    assert list_pool(conn, status=None) == []
    conn.close()


def test_pool_dedupe(tmp_path: Path) -> None:
    from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery

    conn = init_db(tmp_path / "t.sqlite3")
    c1 = add_seller_from_discovery(
        conn, seller_id="111", nickname="n", source_keyword="k1", source_item_id="i1"
    )
    c2 = add_seller_from_discovery(
        conn, seller_id="111", nickname="n", source_keyword="k2", source_item_id="i2"
    )
    conn.commit()
    assert c1 is True
    assert c2 is False
    rows = list_pool(conn)
    assert len(rows) == 1
    entries = conn.execute("SELECT source_keyword FROM seller_pool_entries").fetchall()
    assert {e["source_keyword"] for e in entries} == {"k1", "k2"}
    conn.close()

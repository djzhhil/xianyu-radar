"""Offline discover + pool integration."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.discovery.seller_discovery import discover_sellers
from xianyu_radar.sellers.pool import list_pool
from xianyu_radar.storage.db import init_db

FIXTURES = Path(__file__).parent / "fixtures"


def test_discover_from_fixture_without_seller_id(tmp_path: Path) -> None:
    """Search fixture has no seller_id; items saved, pool skip counted."""
    conn = init_db(tmp_path / "t.sqlite3")
    summary = discover_sellers(
        conn,
        "Sony A7M4",
        fixture_path=str(FIXTURES / "search_results.json"),
        enrich=False,
    )
    assert summary["item_count"] == 1
    assert summary["skipped_no_seller"] == 1
    # placeholder seller for FK
    items = conn.execute("SELECT item_id, seller_id FROM items").fetchall()
    assert len(items) == 1
    conn.close()


def test_pool_dedupe(tmp_path: Path) -> None:
    from xianyu_radar.sellers.pool import add_seller_from_discovery

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

"""Schema / migrate tests for Task 01."""

from __future__ import annotations

from pathlib import Path

from xianyu_radar.config import SCHEMA_VERSION
from xianyu_radar.storage.db import get_schema_version, init_db, table_names

REQUIRED_TABLES = {
    "meta",
    "watch_keywords",
    "sellers",
    "seller_pool_entries",
    "items",
    "item_snapshots",
    "item_events",
    "discovery_runs",
    "scans",
    "candidates",
    "candidate_sellers",
}


def test_init_db_creates_required_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "radar.sqlite3"
    conn = init_db(db_path)
    names = table_names(conn)
    missing = REQUIRED_TABLES - names
    assert not missing, f"missing tables: {missing}"
    assert get_schema_version(conn) == SCHEMA_VERSION
    conn.close()


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "radar.sqlite3"
    conn1 = init_db(db_path)
    conn1.close()
    conn2 = init_db(db_path)
    assert get_schema_version(conn2) == SCHEMA_VERSION
    assert REQUIRED_TABLES <= table_names(conn2)
    conn2.close()

"""Schema / migrate tests for Task 01."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from xianyu_radar.config import SCHEMA_VERSION
from xianyu_radar.infrastructure.storage.db import get_schema_version, init_db, table_names

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


def test_v1_database_migrates_without_losing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    schema = (Path(__file__).parents[1] / "src/xianyu_radar/infrastructure/storage/schema.sql").read_text()
    with sqlite3.connect(db_path) as old:
        old.executescript(schema)
        old.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '1')")
        old.execute(
            "INSERT INTO sellers(seller_id, first_seen_at, last_seen_at) VALUES ('s1', 't', 't')"
        )

    conn = init_db(db_path)
    assert get_schema_version(conn) == SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 1
    assert "missing_count" in {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    assert "expected_count" in {row["name"] for row in conn.execute("PRAGMA table_info(scans)")}
    conn.close()


def test_v2_candidates_are_flagged_without_changing_review_status(tmp_path: Path) -> None:
    db_path = tmp_path / "v2.sqlite3"
    storage = Path(__file__).parents[1] / "src/xianyu_radar/infrastructure/storage"
    with sqlite3.connect(db_path) as old:
        old.executescript((storage / "schema.sql").read_text())
        old.executescript((storage / "migrations/0002_scan_quality.sql").read_text())
        old.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '2')")
        old.execute(
            "INSERT INTO candidates(normalized_title, first_seen_at, last_seen_at, status) "
            "VALUES ('old item', 't', 't', 'rejected')"
        )

    conn = init_db(db_path)
    row = conn.execute("SELECT quality_flag, status FROM candidates").fetchone()
    assert tuple(row) == ("legacy_unverified", "rejected")
    assert get_schema_version(conn) == SCHEMA_VERSION
    conn.close()

"""Schema / migrate tests for Task 01."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

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


@pytest.mark.parametrize("missing_columns", [(), ("pooled",), ("pool_entry_id",), ("pooled", "pool_entry_id")])
def test_v9_discovery_pool_compat_preserves_records(tmp_path, missing_columns):
    db_path = tmp_path / "v9.sqlite3"
    conn = init_db(db_path)
    conn.execute("INSERT INTO discovery_runs(id,keyword,started_at,status) VALUES ('old','FDE','t','ok')")
    conn.execute(
        "INSERT INTO discovery_items(run_id,item_id,title,price,url,resolution,pooled,pool_entry_id) "
        "VALUES ('old','123','item','10','https://www.goofish.com/item?id=123','search',1,42)"
    )
    for column in missing_columns:
        conn.execute(f"ALTER TABLE discovery_items DROP COLUMN {column}")
    conn.execute("UPDATE meta SET value='9' WHERE key='schema_version'")
    conn.commit()
    conn.close()

    for _ in range(2):
        conn = init_db(db_path)
        row = conn.execute("SELECT item_id,title,pooled,pool_entry_id FROM discovery_items").fetchone()
        assert tuple(row) == ("123", "item", 0 if "pooled" in missing_columns else 1,
                              None if "pool_entry_id" in missing_columns else 42)
        assert get_schema_version(conn) == SCHEMA_VERSION
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.close()


@pytest.mark.parametrize("missing_column", [True, False])
def test_v10_scan_compat_preserves_history_and_saves_images(tmp_path, monkeypatch, missing_column):
    from xianyu_radar.infrastructure.goofish.session import Session
    from xianyu_radar.modules.scan.service import scan_seller

    db_path = tmp_path / "v10.sqlite3"
    conn = init_db(db_path)
    conn.execute(
        "INSERT INTO scan_pages(scan_id,page_number,total_type,card_count,parsed_count,unique_count,next_field) "
        "VALUES ('old',1,'int',1,1,1,'nextPage')"
    )
    if missing_column:
        conn.execute("ALTER TABLE scan_pages DROP COLUMN next_field")
    conn.execute("UPDATE meta SET value='10' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    conn = init_db(db_path)
    row = conn.execute("SELECT card_count,next_field FROM scan_pages WHERE scan_id='old'").fetchone()
    assert tuple(row) == (1, None if missing_column else "nextPage")

    image = "https://img.alicdn.com/example.jpg"
    payload = {"data": {"totalCount": 1, "nextPage": False, "cardList": [
        {"cardData": {"id": "123", "title": "item", "picInfo": {"picUrl": image}}}
    ]}}
    monkeypatch.setattr("xianyu_radar.modules.scan.fetcher.call_mtop", lambda *args, **kwargs: payload)
    result = scan_seller(conn, Session("cookie", "token", "test"), "456")
    assert result["status"] == "ok"
    assert conn.execute("SELECT image FROM items WHERE item_id='123'").fetchone()[0] == image
    assert conn.execute("SELECT image FROM item_snapshots WHERE item_id='123'").fetchone()[0] == image
    assert conn.execute("SELECT next_field FROM scan_pages WHERE scan_id=?", (result["scan_id"],)).fetchone()[0] == "nextPage"
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    conn = init_db(db_path)
    assert get_schema_version(conn) == SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM scan_pages").fetchone()[0] == 2
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
        old.execute("INSERT INTO items(item_id,seller_id,first_seen_at,last_seen_at) VALUES ('i1','s1','t','t')")
        old.execute("INSERT INTO item_snapshots(item_id,seller_id,captured_at,scan_id) VALUES ('i1','s1','t','old')")

    conn = init_db(db_path)
    assert get_schema_version(conn) == SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 1
    assert "missing_count" in {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    assert "expected_count" in {row["name"] for row in conn.execute("PRAGMA table_info(scans)")}
    assert tuple(conn.execute("SELECT notes,tags FROM sellers WHERE seller_id='s1'").fetchone()) == ("", "[]")
    assert conn.execute("SELECT image FROM items WHERE item_id='i1'").fetchone()[0] == ""
    assert conn.execute("SELECT image FROM item_snapshots WHERE scan_id='old'").fetchone()[0] == ""
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
    assert conn.execute("SELECT COUNT(*) FROM candidate_sources").fetchone()[0] == 0
    assert get_schema_version(conn) == SCHEMA_VERSION
    conn.close()


def test_v3_runs_migrate_without_losing_history(tmp_path: Path) -> None:
    db_path = tmp_path / "v3.sqlite3"
    storage = Path(__file__).parents[1] / "src/xianyu_radar/infrastructure/storage"
    with sqlite3.connect(db_path) as old:
        old.executescript((storage / "schema.sql").read_text())
        old.executescript((storage / "migrations/0002_scan_quality.sql").read_text())
        old.executescript((storage / "migrations/0003_candidate_quality.sql").read_text())
        old.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '3')")
        old.execute(
            "INSERT INTO discovery_runs(id, keyword, started_at, item_count, seller_count, status) "
            "VALUES ('old', 'camera', 't', 2, 1, 'ok')"
        )
    conn = init_db(db_path)
    run = conn.execute("SELECT item_count, seller_count, status, page_count "
                       "FROM discovery_runs WHERE id='old'").fetchone()
    assert tuple(run) == (2, 1, "ok", 0)
    assert {"discovery_pages", "discovery_items", "discovery_entries", "scan_pages"} <= table_names(conn)
    conn.close()


@pytest.mark.parametrize("missing_column", [True, False])
def test_v8_discovery_compat_preserves_existing_runs_and_counts(tmp_path, missing_column):
    db_path = tmp_path / "v8.sqlite3"
    conn = init_db(db_path)
    conn.execute("INSERT INTO discovery_runs(id,keyword,started_at,status,item_count,unparsed_count) VALUES ('old','FDE','t','ok',3,7)")
    if missing_column:
        conn.execute("ALTER TABLE discovery_runs DROP COLUMN unparsed_count")
    conn.execute("UPDATE meta SET value='8' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    conn = init_db(db_path)
    assert tuple(conn.execute("SELECT keyword,status,item_count,unparsed_count FROM discovery_runs WHERE id='old'").fetchone()) == ("FDE", "ok", 3, 0 if missing_column else 7)
    assert get_schema_version(conn) == SCHEMA_VERSION
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    conn = init_db(db_path)
    assert conn.execute("SELECT COUNT(*) FROM discovery_runs").fetchone()[0] == 1
    conn.close()

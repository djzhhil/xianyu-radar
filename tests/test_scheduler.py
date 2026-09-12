"""Scheduler unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from xianyu_radar.auth.session import Session
from xianyu_radar.scheduler.runner import is_auth_paused, run_pool_once
from xianyu_radar.sellers.pool import add_seller_from_discovery
from xianyu_radar.storage.db import init_db


def test_run_pool_respects_auth_pause(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    add_seller_from_discovery(
        conn, seller_id="111", nickname="n", source_keyword="k", source_item_id="i"
    )
    conn.commit()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused','1')")
    conn.commit()
    assert is_auth_paused(conn)
    session = Session(cookies="a=1", token="t", source="t")
    results = run_pool_once(conn, session)
    assert results[0]["status"] == "skipped"
    conn.close()


def test_run_pool_calls_scan(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    add_seller_from_discovery(
        conn, seller_id="222", nickname="n", source_keyword="k", source_item_id="i"
    )
    conn.commit()
    session = Session(cookies="a=1", token="t", source="t")
    with patch(
        "xianyu_radar.scheduler.runner.scan_seller",
        return_value={"status": "ok", "events": []},
    ) as mocked:
        results = run_pool_once(conn, session)
    mocked.assert_called_once()
    assert results[0]["status"] == "ok"
    conn.close()

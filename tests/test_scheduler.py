"""Scheduler unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from xianyu_radar.auth.session import Session
from xianyu_radar.scheduler.runner import (
    clear_auth_paused,
    is_auth_paused,
    run_loop,
    run_pool_once,
)
from xianyu_radar.sellers.pool import add_seller_from_discovery
from xianyu_radar.storage.db import init_db


def _mk_session() -> Session:
    return Session(cookies="a=1", token="t", source="t")


def test_run_pool_respects_auth_pause(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    add_seller_from_discovery(
        conn, seller_id="111", nickname="n", source_keyword="k", source_item_id="i"
    )
    conn.commit()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused','1')")
    conn.commit()
    assert is_auth_paused(conn)
    session = _mk_session()
    results = run_pool_once(conn, session)
    assert results[0]["status"] == "skipped"
    conn.close()


def test_run_pool_calls_scan(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    add_seller_from_discovery(
        conn, seller_id="222", nickname="n", source_keyword="k", source_item_id="i"
    )
    conn.commit()
    session = _mk_session()
    with patch(
        "xianyu_radar.scheduler.runner.scan_seller",
        return_value={"status": "ok", "events": []},
    ) as mocked:
        results = run_pool_once(conn, session)
    mocked.assert_called_once()
    assert results[0]["status"] == "ok"
    conn.close()


def test_run_loop_recovers_from_auth_pause(tmp_path: Path) -> None:
    """auth_paused + expired broker lease no longer stalls the loop forever.

    Each round the loop should try refresh_session; on success it must
    clear auth_paused and actually scan the pool.
    """
    conn = init_db(tmp_path / "t.sqlite3")
    add_seller_from_discovery(
        conn, seller_id="333", nickname="n", source_keyword="k", source_item_id="i"
    )
    conn.commit()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused','1')")
    conn.commit()
    assert is_auth_paused(conn)

    fresh = _mk_session()
    notices: list[str] = []

    with patch(
        "xianyu_radar.scheduler.runner.scan_seller",
        return_value={"status": "ok", "events": []},
    ) as mocked:
        run_loop(
            conn,
            _mk_session(),
            interval_sec=0,
            jitter_sec=0,
            max_rounds=1,
            refresh_session=lambda _old: fresh,
            on_notice=notices.append,
        )

    # refresh path taken: pool actually scanned, flag cleared
    mocked.assert_called_once()
    assert not is_auth_paused(conn)
    assert any("auth_paused cleared" in n for n in notices)
    conn.close()


def test_run_loop_survives_refresh_failure(tmp_path: Path) -> None:
    """A failing refresh must not crash the loop; it stays paused."""
    conn = init_db(tmp_path / "t.sqlite3")
    add_seller_from_discovery(
        conn, seller_id="444", nickname="n", source_keyword="k", source_item_id="i"
    )
    conn.commit()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused','1')")
    conn.commit()

    def _boom(_old: Session) -> Session:
        raise RuntimeError("broker down")

    with patch("xianyu_radar.scheduler.runner.scan_seller") as mocked:
        run_loop(
            conn,
            _mk_session(),
            interval_sec=0,
            jitter_sec=0,
            max_rounds=1,
            refresh_session=_boom,
            on_notice=lambda _m: None,
        )
    mocked.assert_not_called()  # still paused, skipped without scanning
    assert is_auth_paused(conn)
    conn.close()


def test_run_loop_clear_auth_paused_helper(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "t.sqlite3")
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('auth_paused','1')")
    conn.commit()
    assert is_auth_paused(conn)
    clear_auth_paused(conn)
    assert not is_auth_paused(conn)
    conn.close()

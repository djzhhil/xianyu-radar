"""Background-ish pool scanner with jitter and backoff."""

from __future__ import annotations

import random
import sqlite3
import time
from typing import Callable

from xianyu_radar.auth.session import Session
from xianyu_radar.config import (
    DEFAULT_JITTER_SEC,
    DEFAULT_SELLER_SCAN_INTERVAL_SEC,
    MTOP_MIN_INTERVAL_SEC,
)
from xianyu_radar.sellers.monitor import scan_seller
from xianyu_radar.sellers.pool import list_pool


def is_auth_paused(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value FROM meta WHERE key='auth_paused'"
    ).fetchone()
    return bool(row and row["value"] in ("1", "true", "True"))


def clear_auth_paused(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM meta WHERE key='auth_paused'")
    conn.commit()


def run_pool_once(
    conn: sqlite3.Connection,
    session: Session,
    *,
    on_result: Callable[[dict], None] | None = None,
) -> list[dict]:
    if is_auth_paused(conn):
        return [{"status": "skipped", "error_kind": "auth_paused"}]
    sellers, _total = list_pool(conn, status="watching")
    results = []
    for idx, s in enumerate(sellers):
        # skip unknown placeholders
        if str(s["seller_id"]).startswith("unknown:"):
            continue
        if idx > 0:
            time.sleep(max(float(MTOP_MIN_INTERVAL_SEC), 0.5))
        result = scan_seller(conn, session, s["seller_id"])
        results.append(result)
        if on_result:
            on_result(result)
        if result.get("error_kind") == "auth":
            break
    return results


def run_loop(
    conn: sqlite3.Connection,
    session: Session,
    *,
    interval_sec: float = DEFAULT_SELLER_SCAN_INTERVAL_SEC,
    jitter_sec: float = DEFAULT_JITTER_SEC,
    max_rounds: int | None = None,
    on_result: Callable[[dict], None] | None = None,
    refresh_session: Callable[[Session], Session] | None = None,
    on_notice: Callable[[str], None] | None = None,
) -> Session:
    """Run the pool scanner forever.

    Broker leases expire; a Session loaded once at startup goes stale.
    When ``refresh_session`` is provided, each round tries to obtain a
    fresh session first. A successful refresh also clears the
    ``auth_paused`` circuit breaker so a temporary auth failure no
    longer stalls the loop forever.
    """
    notice = on_notice or (lambda msg: None)
    rounds = 0
    while True:
        if refresh_session is not None and is_auth_paused(conn):
            try:
                refreshed = refresh_session(session)
            except Exception as e:  # noqa: BLE001 - keep the loop alive
                notice(f"session refresh failed: {e}")
                refreshed = None
            if refreshed is not None and refreshed.ok:
                session = refreshed
                clear_auth_paused(conn)
                notice("session refreshed; auth_paused cleared")
        run_pool_once(conn, session, on_result=on_result)
        rounds += 1
        if max_rounds is not None and rounds >= max_rounds:
            break
        sleep_for = interval_sec + random.uniform(0, jitter_sec)
        # simple backoff if auth paused
        if is_auth_paused(conn):
            sleep_for = max(sleep_for, interval_sec * 3)
        time.sleep(sleep_for)
    return session

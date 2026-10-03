"""Background-ish pool scanner with jitter and backoff."""

from __future__ import annotations

import random
import sqlite3
import time
from typing import Callable

from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.goofish.errors import STOP_KINDS, HelperError
from xianyu_radar.infrastructure.helper.session_provider import session_operation
from xianyu_radar.infrastructure.storage.auth_state import is_auth_paused
from xianyu_radar.config import (
    DEFAULT_JITTER_SEC,
    DEFAULT_SELLER_SCAN_INTERVAL_SEC,
)
from xianyu_radar.modules.scan.service import scan_seller
from xianyu_radar.infrastructure.storage.seller_repository import list_pool


def run_pool_once(
    conn: sqlite3.Connection,
    session: Session,
    *,
    on_result: Callable[[dict], None] | None = None,
    between_sellers_sec: float = 2.0,
    jitter_sec: float = 1.0,
) -> list[dict]:
    if is_auth_paused(conn):
        return [{"status": "skipped", "error_kind": "auth_paused"}]
    sellers = list_pool(conn, status="watching")
    results = []
    scanned = 0
    for s in sellers:
        # skip unknown placeholders
        if str(s["seller_id"]).startswith("unknown:"):
            continue
        if scanned:
            time.sleep(max(0.0, between_sellers_sec + random.uniform(0, jitter_sec)))
        result = scan_seller(conn, session, s["seller_id"])
        scanned += 1
        results.append(result)
        if on_result:
            on_result(result)
        if result.get("error_kind") in STOP_KINDS or session.stop_kind:
            break
    return results


def run_loop(
    conn: sqlite3.Connection,
    *,
    interval_sec: float = DEFAULT_SELLER_SCAN_INTERVAL_SEC,
    jitter_sec: float = DEFAULT_JITTER_SEC,
    max_rounds: int | None = None,
    on_result: Callable[[dict], None] | None = None,
) -> bool:
    rounds = 0
    while True:
        if is_auth_paused(conn):
            if on_result:
                on_result({"status": "skipped", "error_kind": "auth_paused"})
            return False
        try:
            with session_operation() as session:
                results = run_pool_once(conn, session, on_result=on_result)
            if session.stop_kind or any(r.get("error_kind") in STOP_KINDS for r in results):
                return False
        except HelperError as exc:
            if on_result:
                on_result({"status": "failed", "error_kind": exc.kind})
            return False
        rounds += 1
        if max_rounds is not None and rounds >= max_rounds:
            return True
        sleep_for = interval_sec + random.uniform(0, jitter_sec)
        time.sleep(sleep_for)

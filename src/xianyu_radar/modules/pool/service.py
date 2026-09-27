"""Public seller pool feature operations."""

from __future__ import annotations

import sqlite3

from xianyu_radar.infrastructure.storage.seller_repository import (
    list_pool,
    set_seller_status,
)

ALLOWED_STATUSES = frozenset({"watching", "paused", "dropped"})


def change_status(conn: sqlite3.Connection, seller_id: str, status: str) -> bool:
    if status not in ALLOWED_STATUSES:
        raise ValueError("invalid status")
    return set_seller_status(conn, seller_id, status)

"""Public candidate feature operations."""

from __future__ import annotations

import sqlite3

from xianyu_radar.modules.candidates.repository import (
    count_candidates,
    list_candidates,
    set_candidate_status,
)

ALLOWED_STATUSES = frozenset({"new", "watching", "testing", "validated", "rejected"})


def change_status(conn: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    if status not in ALLOWED_STATUSES:
        raise ValueError("invalid status")
    return set_candidate_status(conn, candidate_id, status)

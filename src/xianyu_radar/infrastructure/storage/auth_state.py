"""Persistent auth pause flag shared by authentication and scanning."""

from __future__ import annotations

import sqlite3


def is_auth_paused(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key='auth_paused'").fetchone()
    return bool(row and row["value"] in ("1", "true", "True"))


def clear_auth_paused(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM meta WHERE key='auth_paused'")
    conn.commit()

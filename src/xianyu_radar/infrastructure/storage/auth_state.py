"""Persistent auth pause flag shared by authentication and scanning."""

from __future__ import annotations

import sqlite3


def is_auth_paused(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key='auth_paused'").fetchone()
    return bool(row and row["value"] in ("1", "true", "True"))


def clear_auth_paused(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM meta WHERE key IN ('auth_paused','auth_pause_reason')")
    conn.commit()


def auth_pause_reason(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key='auth_pause_reason'").fetchone()
    return row["value"] if row and row["value"] in {"auth", "verification_required"} else None


def set_auth_paused(conn: sqlite3.Connection, reason: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('auth_paused','1')")
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('auth_pause_reason',?)",
                 (reason if reason in {"auth", "verification_required"} else "auth",))
    conn.commit()

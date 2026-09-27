"""Read and update candidate records."""

from __future__ import annotations

import sqlite3


def list_candidates(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if since_iso:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE last_seen_at >= ? "
            "ORDER BY score DESC, last_seen_at DESC LIMIT ?",
            (since_iso, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM candidates ORDER BY score DESC, last_seen_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        candidate = dict(row)
        sellers = conn.execute(
            "SELECT seller_id FROM candidate_sellers WHERE candidate_id=?",
            (candidate["candidate_id"],),
        ).fetchall()
        candidate["source_sellers"] = [seller["seller_id"] for seller in sellers]
        out.append(candidate)
    return out


def set_candidate_status(conn: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    cursor = conn.execute(
        "UPDATE candidates SET status=? WHERE candidate_id=?", (status, candidate_id)
    )
    conn.commit()
    return cursor.rowcount > 0

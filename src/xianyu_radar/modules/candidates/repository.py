"""Read and update candidate records."""

from __future__ import annotations

import sqlite3


def list_candidates(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    quality_flag: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    where = []
    params: list[object] = []
    if since_iso:
        where.append("last_seen_at >= ?")
        params.append(since_iso)
    if quality_flag:
        where.append("quality_flag = ?")
        params.append(quality_flag)
    clause = " WHERE " + " AND ".join(where) if where else ""
    rows = conn.execute(
        "SELECT * FROM candidates" + clause
        + " ORDER BY score DESC, last_seen_at DESC, candidate_id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
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


def count_candidates(
    conn: sqlite3.Connection, *, since_iso: str | None = None, quality_flag: str | None = None
) -> int:
    where = []
    params: list[object] = []
    if since_iso:
        where.append("last_seen_at >= ?")
        params.append(since_iso)
    if quality_flag:
        where.append("quality_flag = ?")
        params.append(quality_flag)
    clause = " WHERE " + " AND ".join(where) if where else ""
    return conn.execute("SELECT COUNT(*) FROM candidates" + clause, params).fetchone()[0]


def set_candidate_status(conn: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    cursor = conn.execute(
        "UPDATE candidates SET status=? WHERE candidate_id=?", (status, candidate_id)
    )
    conn.commit()
    return cursor.rowcount > 0

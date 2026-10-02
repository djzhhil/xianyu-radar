"""Read and update candidate records."""

from __future__ import annotations

import sqlite3


def _candidate_filters(
    since_iso: str | None, quality_flag: str | None, status: str | None = None
) -> tuple[str, list[object]]:
    where = []
    params: list[object] = []
    if since_iso:
        where.append("last_seen_at >= ?")
        params.append(since_iso)
    if quality_flag:
        where.append("quality_flag = ?")
        params.append(quality_flag)
    if status:
        where.append("status = ?")
        params.append(status)
    return (" WHERE " + " AND ".join(where) if where else ""), params


def list_candidates(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    quality_flag: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    clause, params = _candidate_filters(since_iso, quality_flag, status)
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
        types = conn.execute(
            "SELECT source_type,COUNT(*) AS count FROM candidate_sources WHERE candidate_id=? GROUP BY source_type",
            (candidate["candidate_id"],),
        ).fetchall()
        candidate["source_types"] = {row["source_type"]: row["count"] for row in types}
        out.append(candidate)
    return out


def list_sources(conn: sqlite3.Connection, candidate_id: int, *, limit: int = 20, offset: int = 0) -> dict | None:
    if not conn.execute("SELECT 1 FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone():
        return None
    total = conn.execute("SELECT COUNT(*) FROM candidate_sources WHERE candidate_id=?", (candidate_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT c.*,s.nickname FROM candidate_sources c LEFT JOIN sellers s ON s.seller_id=c.seller_id "
        "WHERE candidate_id=? ORDER BY source_id DESC LIMIT ? OFFSET ?", (candidate_id, limit, offset),
    ).fetchall()
    return {"sources": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def count_candidates(
    conn: sqlite3.Connection,
    *,
    since_iso: str | None = None,
    quality_flag: str | None = None,
    status: str | None = None,
) -> int:
    clause, params = _candidate_filters(since_iso, quality_flag, status)
    return conn.execute("SELECT COUNT(*) FROM candidates" + clause, params).fetchone()[0]


def summarize_candidates(
    conn: sqlite3.Connection, *, since_iso: str | None = None, quality_flag: str | None = None
) -> dict:
    clause, params = _candidate_filters(since_iso, quality_flag)
    rows = conn.execute(
        "SELECT status, COUNT(*) AS count, "
        "SUM(CASE WHEN seller_count >= 2 THEN 1 ELSE 0 END) AS multi_seller "
        "FROM candidates" + clause + " GROUP BY status",
        params,
    ).fetchall()
    return {
        "total": sum(row["count"] for row in rows),
        "multi_seller": sum(row["multi_seller"] for row in rows),
        "by_status": {row["status"]: row["count"] for row in rows},
    }


def set_candidate_status(conn: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    cursor = conn.execute(
        "UPDATE candidates SET status=? WHERE candidate_id=?", (status, candidate_id)
    )
    conn.commit()
    return cursor.rowcount > 0

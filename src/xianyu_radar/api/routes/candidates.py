"""Candidates endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from xianyu_radar.api.deps import clamp_page, get_db, page_meta, parse_since
from xianyu_radar.candidates.detector import list_candidates

router = APIRouter()


class CandidateStatusBody(BaseModel):
    status: str


@router.get("")
def get_candidates(
    since: str = "24h",
    page: int = 1,
    page_size: int = 20,
    limit: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if limit is not None and page == 1:
        page_size = limit
    page, page_size, offset = clamp_page(page, page_size, max_size=100, default_size=20)
    since_iso = parse_since(since) if since else None
    rows, total = list_candidates(
        conn, since_iso=since_iso, limit=page_size, offset=offset
    )
    meta = page_meta(total, page, page_size)
    return {"count": len(rows), "since": since, "candidates": rows, **meta}


@router.patch("/{candidate_id}")
def patch_candidate(
    candidate_id: int,
    body: CandidateStatusBody,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    allowed = {"new", "watching", "testing", "validated", "rejected"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail="invalid status")
    row = conn.execute(
        "SELECT candidate_id FROM candidates WHERE candidate_id=?", (candidate_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    conn.execute(
        "UPDATE candidates SET status=? WHERE candidate_id=?",
        (body.status, candidate_id),
    )
    conn.commit()
    return {"candidate_id": candidate_id, "status": body.status}

"""Candidates endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from xianyu_radar.api.deps import get_db, parse_since
from xianyu_radar.candidates.detector import list_candidates

router = APIRouter()


class CandidateStatusBody(BaseModel):
    status: str


@router.get("")
def get_candidates(
    since: str = "24h",
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = list_candidates(conn, since_iso=parse_since(since), limit=limit)
    return {"count": len(rows), "since": since, "candidates": rows}


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

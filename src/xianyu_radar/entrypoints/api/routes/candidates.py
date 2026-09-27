"""Candidates endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from xianyu_radar.entrypoints.api.deps import get_db, parse_since
from xianyu_radar.modules.candidates import service

router = APIRouter()


class CandidateStatusBody(BaseModel):
    status: str


@router.get("")
def get_candidates(
    since: str = "24h",
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = service.list_candidates(conn, since_iso=parse_since(since), limit=limit)
    return {"count": len(rows), "since": since, "candidates": rows}


@router.patch("/{candidate_id}")
def patch_candidate(
    candidate_id: int,
    body: CandidateStatusBody,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if body.status not in service.ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    if not service.change_status(conn, candidate_id, body.status):
        raise HTTPException(status_code=404, detail="not found")
    return {"candidate_id": candidate_id, "status": body.status}

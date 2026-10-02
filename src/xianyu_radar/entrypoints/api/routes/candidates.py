"""Candidates endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from xianyu_radar.entrypoints.api.deps import get_db, parse_since
from xianyu_radar.modules.candidates import service

router = APIRouter()


class CandidateStatusBody(BaseModel):
    status: str


@router.get("/{candidate_id}/sources")
def get_sources(
    candidate_id: int, limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0, conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    result = service.list_sources(conn, candidate_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return result


@router.get("")
def get_candidates(
    since: str = "24h",
    quality: Literal["all", "normal", "legacy_unverified"] = "all",
    status: Literal["all", "new", "watching", "testing", "validated", "rejected"] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    since_iso = parse_since(since)
    quality_flag = None if quality == "all" else quality
    status_filter = None if status == "all" else status
    rows = service.list_candidates(
        conn,
        since_iso=since_iso,
        quality_flag=quality_flag,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    total = service.count_candidates(
        conn, since_iso=since_iso, quality_flag=quality_flag, status=status_filter
    )
    summary = service.summarize_candidates(conn, since_iso=since_iso, quality_flag=quality_flag)
    return {
        "count": len(rows), "total": total, "since": since,
        "quality": quality, "status": status, "offset": offset,
        "summary": summary, "candidates": rows,
    }


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

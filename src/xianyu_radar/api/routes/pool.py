"""Seller pool endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from xianyu_radar.api.deps import get_db
from xianyu_radar.sellers.pool import list_pool, set_seller_status

router = APIRouter()


class StatusBody(BaseModel):
    status: str


@router.get("")
def get_pool(
    all: bool = False,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = list_pool(conn, status=None if all else "watching")
    return {"count": len(rows), "sellers": rows}


@router.patch("/{seller_id}")
def patch_seller(
    seller_id: str,
    body: StatusBody,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if body.status not in {"watching", "paused", "dropped"}:
        raise HTTPException(status_code=400, detail="invalid status")
    row = conn.execute(
        "SELECT seller_id FROM sellers WHERE seller_id=?", (seller_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="seller not found")
    set_seller_status(conn, seller_id, body.status)
    return {"seller_id": seller_id, "status": body.status}

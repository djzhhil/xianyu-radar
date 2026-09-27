"""Seller pool endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from xianyu_radar.entrypoints.api.deps import get_db
from xianyu_radar.modules.pool import service

router = APIRouter()


class StatusBody(BaseModel):
    status: str


@router.get("")
def get_pool(
    all: bool = False,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = service.list_pool(conn, status=None if all else "watching")
    return {"count": len(rows), "sellers": rows}


@router.patch("/{seller_id}")
def patch_seller(
    seller_id: str,
    body: StatusBody,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if body.status not in service.ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    if not service.change_status(conn, seller_id, body.status):
        raise HTTPException(status_code=404, detail="seller not found")
    return {"seller_id": seller_id, "status": body.status}

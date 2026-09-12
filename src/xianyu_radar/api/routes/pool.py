"""Seller pool endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xianyu_radar.api.deps import get_db, clamp_page, page_meta
from xianyu_radar.sellers.pool import (
    add_seller_from_discovery,
    list_pool,
    list_seller_items,
    set_seller_status,
)

router = APIRouter()


class StatusBody(BaseModel):
    status: str


class AddSellerBody(BaseModel):
    seller_id: str = Field(..., min_length=1, description="Numeric goofish userId / sellerId")
    nickname: str | None = None
    source_keyword: str | None = None
    status: str = "watching"


@router.get("")
def get_pool(
    all: bool = False,
    page: int = 1,
    page_size: int = 20,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    page, page_size, offset = clamp_page(page, page_size, max_size=100, default_size=20)
    rows, total = list_pool(
        conn,
        status=None if all else "watching",
        limit=page_size,
        offset=offset,
    )
    meta = page_meta(total, page, page_size)
    return {"count": len(rows), "sellers": rows, **meta}


@router.post("")
def add_seller(body: AddSellerBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Manually add a seller when detail enrich is blocked by x5sec."""
    sid = body.seller_id.strip()
    if not sid.isdigit():
        raise HTTPException(status_code=400, detail="seller_id must be numeric")
    if body.status not in {"watching", "paused", "dropped"}:
        raise HTTPException(status_code=400, detail="invalid status")
    created = add_seller_from_discovery(
        conn,
        seller_id=sid,
        nickname=body.nickname,
        source_keyword=body.source_keyword or "manual",
        source_item_id=None,
    )
    set_seller_status(conn, sid, body.status)
    return {"seller_id": sid, "created": created, "status": body.status}


@router.post("/cleanup-unknown")
def cleanup_unknown(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Remove placeholder unknown:* sellers created when enrich fails."""
    unknown = [
        r["seller_id"]
        for r in conn.execute("SELECT seller_id FROM sellers WHERE seller_id LIKE 'unknown:%'")
    ]
    for sid in unknown:
        conn.execute("DELETE FROM seller_pool_entries WHERE seller_id=?", (sid,))
        conn.execute("DELETE FROM item_events WHERE seller_id=?", (sid,))
        conn.execute("DELETE FROM item_snapshots WHERE seller_id=?", (sid,))
        conn.execute("DELETE FROM scans WHERE seller_id=?", (sid,))
        conn.execute("DELETE FROM items WHERE seller_id=?", (sid,))
        conn.execute("DELETE FROM sellers WHERE seller_id=?", (sid,))
    conn.commit()
    return {"removed": len(unknown)}


@router.get("/{seller_id}/items")
def get_seller_items(
    seller_id: str,
    all: bool = False,
    page: int = 1,
    page_size: int = 50,
    limit: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Catalog of what this seller is selling (from last scans / discovery)."""
    if limit is not None and page == 1:
        page_size = limit
    page, page_size, offset = clamp_page(page, page_size, max_size=200, default_size=50)
    row = conn.execute(
        "SELECT seller_id, nickname, status, last_scan_at FROM sellers WHERE seller_id=?",
        (seller_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="seller not found")
    items, total = list_seller_items(
        conn,
        seller_id,
        status=None if all else "active",
        limit=page_size,
        offset=offset,
    )
    meta = page_meta(total, page, page_size)
    return {
        "seller_id": seller_id,
        "nickname": row["nickname"],
        "status": row["status"],
        "last_scan_at": row["last_scan_at"],
        "count": len(items),
        "items": items,
        **meta,
    }


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

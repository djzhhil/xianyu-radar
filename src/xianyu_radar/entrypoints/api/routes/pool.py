"""Seller pool endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from xianyu_radar.entrypoints.api.deps import get_db
from xianyu_radar.modules.pool import service

router = APIRouter()


class StatusBody(BaseModel):
    status: str


class AddSellerBody(BaseModel):
    reference: str = Field(min_length=1, max_length=2048)
    nickname: str | None = Field(default=None, max_length=100)


class SellerMetadataBody(BaseModel):
    notes: str = Field(max_length=2000)
    tags: list[str] = Field(max_length=20)


class CandidateRulesBody(BaseModel):
    exclude_patterns: list[str] = Field(max_length=20)


@router.patch("/{seller_id}/candidate-rules")
def patch_candidate_rules(seller_id: str, body: CandidateRulesBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        updated = service.change_candidate_rules(conn, seller_id, body.exclude_patterns)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not updated:
        raise HTTPException(status_code=404, detail="seller not found in pool")
    return {"updated": True}


@router.get("/{seller_id}/candidate-rules")
def preview_candidate_rules(
    seller_id: str, limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0, conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    result = service.preview_candidate_rules(conn, seller_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail="seller not found in pool")
    return result


@router.patch("/{seller_id}/metadata")
def patch_metadata(
    seller_id: str, body: SellerMetadataBody, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    try:
        updated = service.change_metadata(conn, seller_id, body.notes, body.tags)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not updated:
        raise HTTPException(status_code=404, detail="seller not found in pool")
    return {"seller_id": seller_id, "updated": True}


@router.post("")
def add_seller(body: AddSellerBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return service.add_seller(conn, body.reference, body.nickname)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("")
def get_pool(
    all: bool = False,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = service.list_pool(conn, status=None if all else "watching")
    return {"count": len(rows), "sellers": rows}


@router.get("/{seller_id}")
def get_seller_detail(
    seller_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    query: Annotated[str, Query(max_length=200)] = "",
    item_status: Literal["", "active", "removed", "unknown"] = "",
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    detail = service.get_pool_seller_detail(
        conn, seller_id, limit=limit, offset=offset, query=query.strip(), item_status=item_status
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="seller not found in pool")
    return detail


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

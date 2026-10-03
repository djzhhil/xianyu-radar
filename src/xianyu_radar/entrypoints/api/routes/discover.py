"""Discover endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from xianyu_radar.entrypoints.api.deps import get_db, require_session
from xianyu_radar.modules.discovery.service import discover_sellers, list_discovery_runs
from xianyu_radar.modules.discovery.service import get_discovery_run as read_discovery_run
from xianyu_radar.modules.discovery.keyword_search import DiscoveryParseError

router = APIRouter()


@router.get("/runs")
def get_discovery_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    return list_discovery_runs(conn, limit=limit, offset=offset)


@router.get("/runs/{run_id}")
def get_discovery_run(run_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    result = read_discovery_run(conn, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="发现记录不存在")
    return result


class DiscoverBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(..., min_length=1)
    no_enrich: bool = False
    max_pages: int = Field(default=3, ge=1, le=50)
    resume_run_id: str | None = None


@router.post("")
def discover(body: DiscoverBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        with require_session(conn) as session:
            summary = discover_sellers(
                conn, body.keyword.strip(), session=session,
                enrich=not body.no_enrich, max_pages=body.max_pages,
                resume_run_id=body.resume_run_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DiscoveryParseError as exc:
        raise HTTPException(status_code=502, detail="闲鱼搜索响应无法解析") from exc

    items = summary.pop("items", [])
    return {
        **summary,
        "items": [
            {
                "item_id": i.item_id,
                "title": i.title,
                "price": i.price,
                "url": i.url,
                "seller_id": i.seller_id,
                "seller_nick": i.seller_nick,
            }
            for i in items[:50]
        ],
    }

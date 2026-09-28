"""Events endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from xianyu_radar.entrypoints.api.deps import get_db, parse_since
from xianyu_radar.modules.scan.service import count_events, list_events

router = APIRouter()


@router.get("")
def get_events(
    since: str = "24h",
    seller: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    since_iso = parse_since(since)
    rows = list_events(conn, since_iso=since_iso, seller_id=seller, limit=limit, offset=offset)
    total = count_events(conn, since_iso=since_iso, seller_id=seller)
    return {"count": len(rows), "total": total, "since": since, "offset": offset, "events": rows}

"""Events endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from xianyu_radar.entrypoints.api.deps import get_db, parse_since
from xianyu_radar.modules.scan.service import list_events

router = APIRouter()


@router.get("")
def get_events(
    since: str = "24h",
    seller: str | None = None,
    limit: int = 100,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = list_events(conn, since_iso=parse_since(since), seller_id=seller, limit=limit)
    return {"count": len(rows), "since": since, "events": rows}

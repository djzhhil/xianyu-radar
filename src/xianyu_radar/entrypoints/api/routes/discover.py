"""Discover endpoints."""

from __future__ import annotations

import sqlite3
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from xianyu_radar.entrypoints.api.deps import get_db, require_session
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.modules.discovery.service import discover_sellers, list_discovery_runs
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
    run = conn.execute("SELECT * FROM discovery_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(status_code=404, detail="发现记录不存在")
    pages = conn.execute("SELECT * FROM discovery_pages WHERE run_id=? ORDER BY page_number", (run_id,)).fetchall()
    entries = conn.execute(
        "SELECT page_number, entry_index, outcome, item_ref FROM discovery_entries "
        "WHERE run_id=? ORDER BY page_number, entry_index", (run_id,)
    ).fetchall()
    items = conn.execute(
        "SELECT item_id, seller_id, resolution, error_kind, diagnostic FROM discovery_items "
        "WHERE run_id=? ORDER BY rowid", (run_id,)
    ).fetchall()
    return {"run": dict(run), "pages": [dict(row) for row in pages],
            "entries": [dict(row) for row in entries],
            "items": [{**dict(row), "diagnostic": json.loads(row["diagnostic"])} for row in items]}


class DiscoverBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(..., min_length=1)
    no_enrich: bool = False
    max_pages: int = Field(default=3, ge=1, le=50)
    resume_run_id: str | None = None


def _http_from_mtop(exc: MtopError) -> HTTPException:
    msg = str(exc)
    ret = " ".join(str(x) for x in (exc.ret or []))
    blob = f"{msg} {ret}"
    if "RGV587" in blob or "挤爆" in blob or "稍后重试" in blob:
        return HTTPException(
            status_code=429,
            detail="闲鱼限流/挤爆（RGV587）。请稍后再试，降低频率，或换账号 Cookie。",
        )
    if "FAIL_SYS_USER_VALIDATE" in blob or "x5sec" in blob.lower():
        return HTTPException(
            status_code=403,
            detail="触发滑块/人机验证（x5sec）。请用浏览器打开闲鱼完成验证后重新导出 Cookie。",
        )
    if "SESSION" in blob.upper() or "TOKEN" in blob.upper() or "登录" in blob:
        return HTTPException(status_code=401, detail=f"登录态失效：{msg}")
    return HTTPException(status_code=502, detail=f"闲鱼接口失败：{msg}")


@router.post("")
def discover(body: DiscoverBody, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    session = require_session()
    if session.looks_like_placeholder:
        raise HTTPException(
            status_code=400,
            detail="Cookie 为测试占位符，无法在线发现。请粘贴真实 Cookie。",
        )

    try:
        summary = discover_sellers(
            conn,
            body.keyword.strip(),
            session=session,
            enrich=not body.no_enrich,
            max_pages=body.max_pages,
            resume_run_id=body.resume_run_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DiscoveryParseError as e:
        raise HTTPException(status_code=502, detail=f"闲鱼搜索响应无法解析：{e}") from e
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except MtopError as e:
        raise _http_from_mtop(e) from e

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

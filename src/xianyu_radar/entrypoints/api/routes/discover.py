"""Discover endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from xianyu_radar.entrypoints.api.deps import get_db, require_session
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.modules.discovery.service import discover_sellers

router = APIRouter()


class DiscoverBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(..., min_length=1)
    no_enrich: bool = False


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
        )
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

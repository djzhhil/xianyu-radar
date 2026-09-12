"""Scan endpoints."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from xianyu_radar.api.deps import event_to_dict, get_db, require_session
from xianyu_radar.config import ROOT_DIR
from xianyu_radar.models import SellerItem
from xianyu_radar.scheduler.runner import is_auth_paused, run_pool_once
from xianyu_radar.sellers.fetcher import get_seller_items_from_payload
from xianyu_radar.sellers.monitor import apply_scan_result, scan_seller

router = APIRouter()


class ScanSellerBody(BaseModel):
    fixture: str | None = None
    keyword: str | None = None
    # for demo: inject extra new items after fixture baseline
    extra_items: list[dict] | None = None


@router.post("/seller/{seller_id}")
def scan_one(
    seller_id: str,
    body: ScanSellerBody | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    body = body or ScanSellerBody()
    hints = [k.strip() for k in (body.keyword or "").split(",") if k.strip()] or None

    if body.fixture:
        path = Path(body.fixture)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"fixture not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = get_seller_items_from_payload(payload)
        if body.extra_items:
            for raw in body.extra_items:
                items.append(
                    SellerItem(
                        item_id=str(raw["item_id"]),
                        title=str(raw.get("title") or ""),
                        price=str(raw.get("price") or ""),
                        url=str(raw.get("url") or f"https://www.goofish.com/item?id={raw['item_id']}"),
                    )
                )
        result = apply_scan_result(conn, seller_id, items, keyword_hints=hints)
    else:
        session = require_session()
        if session.looks_like_placeholder:
            raise HTTPException(
                status_code=400,
                detail="Cookie 为测试占位符，无法真实扫描。请到登录态粘贴 goofish 会话，或改用离线 Demo。",
            )
        if is_auth_paused(conn):
            raise HTTPException(
                status_code=409,
                detail="auth 已暂停。请更新 Cookie 后点「清除 auth 暂停」，或先 auth check。",
            )
        result = scan_seller(conn, session, seller_id, keyword_hints=hints)

    events = result.get("events") or []
    return {
        "scan_id": result.get("scan_id"),
        "status": result.get("status"),
        "error_kind": result.get("error_kind"),
        "item_count": result.get("item_count", 0),
        "candidates": result.get("candidates"),
        "events": [event_to_dict(e) for e in events],
    }


@router.post("/pool")
def scan_pool(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    session = require_session()
    if session.looks_like_placeholder:
        raise HTTPException(
            status_code=400,
            detail="Cookie 为测试占位符，无法真实扫描商家池。请粘贴真实登录态，或使用「离线闭环 Demo」。",
        )
    if is_auth_paused(conn):
        raise HTTPException(
            status_code=409,
            detail="auth 已暂停（上次会话失效）。请更新 Cookie 并清除暂停后再扫。",
        )
    try:
        results = run_pool_once(conn, session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scan pool failed: {e}") from e
    out = []
    for r in results:
        events = r.get("events") or []
        out.append(
            {
                "scan_id": r.get("scan_id"),
                "status": r.get("status"),
                "error_kind": r.get("error_kind"),
                "item_count": r.get("item_count", 0),
                "event_count": len(events),
                "events": [event_to_dict(e) for e in events],
            }
        )
    return {"count": len(out), "results": out}

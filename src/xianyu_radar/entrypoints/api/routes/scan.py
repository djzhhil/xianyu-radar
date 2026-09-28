"""Scan endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from xianyu_radar.entrypoints.api.deps import event_to_dict, get_db, require_session
from xianyu_radar.infrastructure.storage.auth_state import is_auth_paused
from xianyu_radar.modules.scan.history import list_scan_runs
from xianyu_radar.modules.scan.runner import run_pool_once
from xianyu_radar.modules.scan.service import scan_seller

router = APIRouter()


@router.get("/runs")
def get_scan_runs(
    seller: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    return list_scan_runs(conn, seller_id=seller, limit=limit, offset=offset)


@router.get("/runs/{scan_id}")
def get_scan_run(scan_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    run = conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
    if not run:
        raise HTTPException(status_code=404, detail="扫描记录不存在")
    pages = conn.execute(
        "SELECT * FROM scan_pages WHERE scan_id=? ORDER BY page_number", (scan_id,)
    ).fetchall()
    return {"run": dict(run), "pages": [dict(page) for page in pages]}


class ScanSellerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str | None = None


@router.post("/seller/{seller_id}")
def scan_one(
    seller_id: str,
    body: ScanSellerBody | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if seller_id.startswith("unknown:"):
        raise HTTPException(status_code=400, detail="占位商家没有真实卖家 ID，无法扫描。")
    body = body or ScanSellerBody()
    hints = [k.strip() for k in (body.keyword or "").split(",") if k.strip()] or None

    session = require_session()
    if session.looks_like_placeholder:
        raise HTTPException(
            status_code=400,
            detail="Cookie 为测试占位符，无法真实扫描。请到登录态粘贴 goofish 会话。",
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
        "expected_count": result.get("expected_count"),
        "page_count": result.get("page_count"),
        "finish_reason": result.get("finish_reason"),
        "candidates": result.get("candidates"),
        "events": [event_to_dict(e) for e in events],
    }


@router.post("/pool")
def scan_pool(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    session = require_session()
    if session.looks_like_placeholder:
        raise HTTPException(
            status_code=400,
            detail="Cookie 为测试占位符，无法真实扫描商家池。请粘贴真实登录态。",
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
                "expected_count": r.get("expected_count"),
                "page_count": r.get("page_count"),
                "finish_reason": r.get("finish_reason"),
                "event_count": len(events),
                "events": [event_to_dict(e) for e in events],
            }
        )
    return {"count": len(out), "results": out}

"""Demo / offline integration helpers — always write to the demo database."""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel, Field

from xianyu_radar.api.deps import event_to_dict
from xianyu_radar.config import ROOT_DIR, paths_for
from xianyu_radar.discovery.seller_discovery import discover_sellers
from xianyu_radar.models import SellerItem
from xianyu_radar.sellers.fetcher import get_seller_items_from_payload
from xianyu_radar.sellers.monitor import apply_scan_result
from xianyu_radar.storage.db import init_db

router = APIRouter()


class DemoBody(BaseModel):
    keyword: str = Field(default="Sony A7M4")
    seller_id: str = Field(default="DEMO_SELLER")


@router.post("/offline-loop")
def offline_loop(body: DemoBody) -> dict:
    """
    Full offline path — isolated in data/demo only (never touches prod).
    1) discover from search fixture
    2) baseline scan from shop fixture
    3) second scan with an extra NEW item → candidate
    """
    demo = paths_for("demo")
    demo["data_dir"].mkdir(parents=True, exist_ok=True)
    conn = init_db(demo["db_path"])
    try:
        search_fx = ROOT_DIR / "tests/fixtures/search_results.json"
        shop_fx = ROOT_DIR / "tests/fixtures/shop_items.json"

        disc = discover_sellers(
            conn,
            body.keyword,
            fixture_path=str(search_fx),
            enrich=False,
        )
        disc.pop("items", None)

        payload = json.loads(shop_fx.read_text(encoding="utf-8"))
        items = get_seller_items_from_payload(payload)
        baseline = apply_scan_result(
            conn, body.seller_id, items, keyword_hints=[body.keyword]
        )
        items2 = items + [
            SellerItem(
                item_id="999000111",
                title="Photoshop 完整教程",
                price="12",
                url="https://www.goofish.com/item?id=999000111",
            )
        ]
        second = apply_scan_result(
            conn, body.seller_id, items2, keyword_hints=[body.keyword]
        )

        return {
            "env": "demo",
            "db_path": str(demo["db_path"]),
            "note": "结果写入 demo 库；切换到 demo 环境后可在 UI 查看",
            "discover": disc,
            "baseline": {
                "scan_id": baseline.get("scan_id"),
                "status": baseline.get("status"),
                "event_count": len(baseline.get("events") or []),
                "events": [event_to_dict(e) for e in (baseline.get("events") or [])],
            },
            "second_scan": {
                "scan_id": second.get("scan_id"),
                "status": second.get("status"),
                "candidates": second.get("candidates"),
                "events": [event_to_dict(e) for e in (second.get("events") or [])],
            },
        }
    finally:
        conn.close()

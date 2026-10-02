"""Public seller pool feature operations."""

from __future__ import annotations

import sqlite3
import re
from urllib.parse import parse_qs, urlsplit

from xianyu_radar.infrastructure.storage.seller_repository import (
    get_pool_seller_detail,
    list_pool,
    set_seller_status,
    add_manual_seller,
)

ALLOWED_STATUSES = frozenset({"watching", "paused", "dropped"})


def add_seller(conn: sqlite3.Connection, reference: str, nickname: str | None = None) -> dict:
    reference = reference.strip()
    seller_id = reference
    if not re.fullmatch(r"[0-9]+", reference):
        parsed = urlsplit(reference)
        query = parse_qs(parsed.query)
        values = query.get("userId", [])
        if (parsed.scheme not in {"http", "https"}
                or parsed.netloc not in {"www.goofish.com", "goofish.com"}
                or parsed.path != "/personal" or len(values) != 1):
            raise ValueError("请输入数字商家 ID 或闲鱼主页链接")
        seller_id = values[0]
    if not re.fullmatch(r"[0-9]{1,32}", seller_id) or int(seller_id) == 0:
        raise ValueError("商家 ID 必须是有效的正整数")
    nickname = (nickname or "").strip() or None
    added = add_manual_seller(conn, seller_id, nickname)
    seller = conn.execute("SELECT status FROM sellers WHERE seller_id=?", (seller_id,)).fetchone()
    return {"seller_id": seller_id, "added": added, "status": seller["status"]}


def change_status(conn: sqlite3.Connection, seller_id: str, status: str) -> bool:
    if status not in ALLOWED_STATUSES:
        raise ValueError("invalid status")
    return set_seller_status(conn, seller_id, status)

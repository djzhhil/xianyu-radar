"""Public seller pool feature operations."""

from __future__ import annotations

import sqlite3
import re
import json
from urllib.parse import parse_qs, urlsplit

from xianyu_radar.infrastructure.storage.seller_repository import (
    get_pool_seller_detail,
    list_pool,
    set_seller_status,
    add_manual_seller,
    set_seller_metadata,
    set_candidate_rules,
)
from xianyu_radar.infrastructure.storage.candidate_repository import match_exclusions, normalize_title

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


def change_metadata(conn: sqlite3.Connection, seller_id: str, notes: str, tags: list[str]) -> bool:
    notes = notes.strip()
    tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    if len(notes) > 2000 or len(tags) > 20 or any(len(tag) > 40 for tag in tags):
        raise ValueError("备注最多 2000 字，标签最多 20 个，每个标签最多 40 字")
    return set_seller_metadata(conn, seller_id, notes, tags)


def change_candidate_rules(conn: sqlite3.Connection, seller_id: str, patterns: list[str]) -> bool:
    cleaned = {}
    for pattern in patterns:
        pattern = pattern.strip()
        key = normalize_title(pattern)
        if not key or not any(char.isalnum() for char in key) or len(pattern) > 80:
            raise ValueError("排除词不能为空或仅含标点，每项最多 80 字")
        cleaned.setdefault(key, pattern)
    if len(cleaned) > 20:
        raise ValueError("最多配置 20 项排除词")
    return set_candidate_rules(conn, seller_id, list(cleaned.values()))


def preview_candidate_rules(conn: sqlite3.Connection, seller_id: str, *, limit: int = 20, offset: int = 0) -> dict | None:
    seller = conn.execute(
        "SELECT candidate_exclude_patterns FROM sellers WHERE seller_id=? AND EXISTS ("
        "SELECT 1 FROM seller_pool_entries WHERE seller_id=? AND active=1)", (seller_id, seller_id),
    ).fetchone()
    if not seller:
        return None
    patterns = json.loads(seller["candidate_exclude_patterns"])
    rows = conn.execute("SELECT item_id,title FROM items WHERE seller_id=? AND status='active' ORDER BY item_id", (seller_id,)).fetchall()
    matches = [{"item_id": row["item_id"], "title": row["title"], "matched_patterns": matched}
               for row in rows if (matched := match_exclusions(row["title"] or "", patterns))]
    return {"exclude_patterns": patterns, "matches": matches[offset:offset + limit], "total": len(matches), "offset": offset, "limit": limit}

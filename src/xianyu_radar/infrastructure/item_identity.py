"""Item ID extraction and Goofish URL normalization shared by item sources."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

ITEM_ID_RE = re.compile(r"(?:(?:itemId|id)=)(\d+)", re.I)
FLEAMARKET_RE = re.compile(r"fleamarket://(?:item|awesome_detail).*?[?&](?:itemId|id)=(\d+)", re.I)


def extract_item_id(*candidates: Any) -> str | None:
    """Extract a stable item id from ids, URLs, or nested dict snippets."""
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            s = str(int(c))
            if s.isdigit():
                return s
        if isinstance(c, str):
            s = c.strip()
            if s.isdigit():
                return s
            m = ITEM_ID_RE.search(s) or FLEAMARKET_RE.search(s)
            if m:
                return m.group(1)
            # query string only
            if "id=" in s or "itemId=" in s:
                parsed = urlparse(s if "://" in s else f"https://x/?{s.lstrip('?')}")
                qs = parse_qs(parsed.query)
                for key in ("itemId", "id"):
                    if key in qs and qs[key]:
                        val = qs[key][0]
                        if str(val).isdigit():
                            return str(val)
        if isinstance(c, dict):
            for key in ("itemId", "item_id", "id"):
                if key in c:
                    got = extract_item_id(c[key])
                    if got:
                        return got
    return None


def normalize_goofish_url(raw: str, item_id: str | None = None) -> str:
    if not raw and item_id:
        return f"https://www.goofish.com/item?id={item_id}"
    url = raw.replace("fleamarket://item", "https://www.goofish.com/item")
    url = url.replace("fleamarket://awesome_detail", "https://www.goofish.com/item")
    if url.startswith("fleamarket://"):
        url = "https://www.goofish.com/" + url.split("://", 1)[1]
    if item_id and "id=" not in url and "itemId=" not in url:
        return f"https://www.goofish.com/item?id={item_id}"
    # normalize itemId= to id=
    if "itemId=" in url and "id=" not in url:
        url = url.replace("itemId=", "id=")
    return url

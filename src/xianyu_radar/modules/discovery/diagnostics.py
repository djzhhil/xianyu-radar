"""Error classification and redacted discovery diagnostics."""

from __future__ import annotations

import hashlib
import json
import re

from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.errors import HelperError, error_kind
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.models import SeedItem


def error_kind_for(exc: Exception) -> str:
    if isinstance(exc, (AuthError, HelperError, MtopError)):
        return error_kind(exc)
    return "parse_failed"


def _seller_fields(source: dict) -> list[str]:
    return sorted(str(key) for key in source
                  if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", str(key))
                  and ("seller" in str(key).lower() or str(key).lower() in {"userid", "user_id"}))


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def search_diagnostic(item: SeedItem, run_id: str) -> str:
    entry = _as_dict(item.raw)
    main = _as_dict(_as_dict(_as_dict(entry.get("data")).get("item")).get("main"))
    ex = _as_dict(main.get("exContent"))
    args = _as_dict(_as_dict(main.get("clickParam")).get("args"))
    jump = _as_dict(_as_dict(_as_dict(ex.get("jump2XianYuHao")).get("clickParam")).get("args"))
    seller_ref = (args.get("seller_id") or args.get("sellerId") or jump.get("seller_id")
                  or jump.get("sellerId") or jump.get("userId"))
    group = f"seller:{seller_ref}" if seller_ref else f"item:{item.item_id}"
    group_ref = hashlib.sha256(f"{run_id}:{group}".encode()).hexdigest()
    source = "unresolved"
    if item.seller_id:
        for label, fields in (("search_args", args), ("search_jump", jump)):
            keys = ("sellerId", "seller_id", "userId") if label == "search_jump" else ("sellerId", "seller_id")
            if any(str(fields.get(key, "")).strip() == item.seller_id for key in keys):
                source = label
                break
        else:
            source = "image_path"
    return json.dumps({"source": source, "group_ref": group_ref,
                       "search_args_fields": _seller_fields(args),
                       "search_jump_fields": _seller_fields(jump)}, ensure_ascii=False)


def detail_diagnostic(detail: dict, seller_id: str | None) -> str:
    fields = sorted(str(key) for key in
                    _as_dict(_as_dict(detail.get("data") or detail).get("sellerDO"))
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", str(key)))
    return json.dumps({"source": "sellerDO" if seller_id else "unresolved",
                       "detail_fields": fields}, ensure_ascii=False)

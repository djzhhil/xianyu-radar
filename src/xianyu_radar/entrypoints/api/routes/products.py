"""Live product detail endpoint."""

import re

from fastapi import APIRouter, HTTPException

from xianyu_radar.entrypoints.api.deps import require_session
from xianyu_radar.modules.products.service import get_detail

router = APIRouter()


@router.get("/{item_id}/detail")
def product_detail(item_id: str) -> dict:
    if not re.fullmatch(r"[0-9]{1,32}", item_id) or int(item_id) == 0:
        raise HTTPException(status_code=400, detail="商品 ID 必须是有效的正整数")
    with require_session() as session:
        return get_detail(session, item_id)

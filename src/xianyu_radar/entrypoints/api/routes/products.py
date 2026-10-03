"""Live product detail endpoint."""

import re

from fastapi import APIRouter, HTTPException

from xianyu_radar.entrypoints.api.deps import require_session
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.modules.products.service import get_detail

router = APIRouter()


@router.get("/{item_id}/detail")
def product_detail(item_id: str) -> dict:
    if not re.fullmatch(r"[0-9]{1,32}", item_id) or int(item_id) == 0:
        raise HTTPException(status_code=400, detail="商品 ID 必须是有效的正整数")
    session = require_session()
    if session.looks_like_placeholder:
        raise HTTPException(status_code=400, detail="请先保存真实闲鱼 Cookie")
    try:
        return get_detail(session, item_id)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="登录态失效，请更新 Cookie 后重试") from exc
    except MtopError as exc:
        message = f"{exc} {exc.ret}".lower()
        if "x5sec" in message or "user_validate" in message:
            raise HTTPException(status_code=403, detail="闲鱼要求人机验证，请在闲鱼完成验证并更新 Cookie 后重试") from exc
        if "rgv587" in message or "挤爆" in message:
            raise HTTPException(status_code=429, detail="闲鱼接口限流，请稍后重试") from exc
        raise HTTPException(status_code=502, detail=f"商品详情获取失败：{exc}") from exc

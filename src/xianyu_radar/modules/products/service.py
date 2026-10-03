"""Read product-only details from Goofish."""

from typing import Any

from xianyu_radar.infrastructure.goofish.mtop import MtopError, call_mtop
from xianyu_radar.infrastructure.goofish.session import Session


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    return None


def parse_detail(payload: dict, item_id: str) -> dict:
    data = payload.get("data")
    item = data.get("itemDO") if isinstance(data, dict) else None
    if not isinstance(item, dict) or not item:
        raise MtopError("商品详情响应缺少 itemDO")
    returned_id = item.get("itemId")
    if returned_id is not None and str(returned_id) != item_id:
        raise MtopError("商品详情返回的商品 ID 不一致")
    price = item.get("soldPrice")
    if price is None or price == "":
        price = item.get("minPrice")
    images = item.get("imageInfos")
    image = next((im["url"] for im in images if isinstance(im, dict)
                  and isinstance(im.get("url"), str)), "") if isinstance(images, list) else ""
    return {
        "item_id": item_id,
        "title": str(item.get("title") or ""),
        "price": str(price) if price is not None else None,
        "published_at": item.get("gmtCreate"),
        "image": image,
        "views": _count(item.get("browseCnt")),
        "wants": _count(item.get("wantCnt")),
        "favorites": _count(item.get("collectCnt")),
        "interactions": _count(item.get("interactFavorCnt")),
        "evaluations": _count(item.get("evaluateCnt")),
    }


def get_detail(session: Session, item_id: str) -> dict:
    payload = call_mtop(
        session, "taobao.idle.pc.detail",
        {"id": item_id, "returnItemDO": True, "needSellerDO": False},
        {"spm_cnt": "a21ybx.item.0.0"},
    )
    return parse_detail(payload, item_id)

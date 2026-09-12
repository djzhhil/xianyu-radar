"""MTOP H5 signed HTTP client (ported from zpl11 xianyu_api.mjs)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from xianyu_radar.auth.session import AuthError, Session
from xianyu_radar.config import MTOP_APP_KEY, MTOP_BASE

JSONP_RE = re.compile(r"^\s*mtopjsonp\d+\s*\((.*)\)\s*;?\s*$", re.DOTALL)


class MtopError(Exception):
    def __init__(self, message: str, *, ret: Any = None, payload: Any = None):
        super().__init__(message)
        self.ret = ret
        self.payload = payload


def create_sign(token: str, ts: str | int, data_str: str, app_key: str = MTOP_APP_KEY) -> str:
    sign_str = f"{token}&{ts}&{app_key}&{data_str}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def call_mtop(
    session: Session,
    api_name: str,
    data: dict[str, Any],
    extra_params: dict[str, str] | None = None,
    *,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    Call mtop.{api_name}. api_name should be without leading 'mtop.'
    e.g. 'idle.web.xyh.item.list' or 'taobao.idlemtopsearch.pc.search'
    """
    if not session.ok:
        raise AuthError("Session incomplete")

    ts = str(int(time.time() * 1000))
    data_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Match browser JSON.stringify closely; use standard dumps with no space
    data_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    sign = create_sign(session.token, ts, data_str)

    params: dict[str, str] = {
        "jsv": "2.7.2",
        "appKey": MTOP_APP_KEY,
        "t": ts,
        "sign": sign,
        "v": "1.0",
        "type": "originaljson",
        "api": f"mtop.{api_name}",
        "dataType": "json",
        "timeout": "20000",
        "accountSite": "xianyu",
        "sessionOption": "AutoLoginOnly",
    }
    if extra_params:
        params.update({k: str(v) for k, v in extra_params.items()})

    url = f"{MTOP_BASE}/mtop.{api_name}/1.0/?{urlencode(params)}"
    body = urlencode({"data": data_str})
    headers = {
        "Cookie": session.cookies,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.goofish.com",
        "Referer": "https://www.goofish.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    owns_client = client is None
    if owns_client:
        # WSL/shell often sets ALL_PROXY=socks5://... without socksio installed.
        # Default to direct connection; set RADAR_HTTP_PROXY to opt into a proxy.
        import os

        proxy = os.environ.get("RADAR_HTTP_PROXY") or os.environ.get("RADAR_HTTPS_PROXY")
        client = httpx.Client(timeout=timeout, trust_env=False, proxy=proxy or None)
    try:
        resp = client.post(url, content=body, headers=headers)
        text = resp.text
        match = JSONP_RE.match(text)
        parsed = json.loads(match.group(1) if match else text)
    except Exception as e:
        raise MtopError(f"MTOP request failed: {e}") from e
    finally:
        if owns_client:
            client.close()

    ret = parsed.get("ret") or []
    ret0 = ret[0] if ret else ""
    if isinstance(ret0, str) and ret0.startswith("SUCCESS"):
        return parsed
    if isinstance(ret0, str) and "FAIL_SYS_USER_VALIDATE" in ret0:
        raise MtopError("x5sec / USER_VALIDATE required", ret=ret, payload=parsed)
    if isinstance(ret0, str) and ("SESSION" in ret0.upper() or "TOKEN" in ret0.upper()):
        raise AuthError(f"Auth failed: {ret0}")
    raise MtopError(f"MTOP error: {ret}", ret=ret, payload=parsed)

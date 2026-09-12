"""MTOP H5 signed HTTP client (ported from zpl11 xianyu_api.mjs)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from xianyu_radar.auth.session import AuthError, Session, auth_mode
from xianyu_radar.config import MTOP_APP_KEY, MTOP_BASE, MTOP_MIN_INTERVAL_SEC

JSONP_RE = re.compile(r"^\s*mtopjsonp\d+\s*\((.*)\)\s*;?\s*$", re.DOTALL)

_pace_lock = threading.Lock()
_last_mtop_at = 0.0


class MtopError(Exception):
    def __init__(self, message: str, *, ret: Any = None, payload: Any = None):
        super().__init__(message)
        self.ret = ret
        self.payload = payload


def create_sign(token: str, ts: str | int, data_str: str, app_key: str = MTOP_APP_KEY) -> str:
    sign_str = f"{token}&{ts}&{app_key}&{data_str}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def _api_kind(api_name: str) -> str:
    name = api_name.lower()
    if "search" in name:
        return "search"
    if "detail" in name:
        return "detail"
    return "list"


def _global_pace(kind: str, session: Session) -> None:
    """Honor broker quotas when present, else config min interval."""
    if auth_mode() == "broker" and session.from_broker:
        try:
            from xianyu_radar.auth.broker_client import get_broker_client

            get_broker_client().pace(kind)
            return
        except Exception:
            pass
    global _last_mtop_at
    interval = float(MTOP_MIN_INTERVAL_SEC)
    with _pace_lock:
        now = time.monotonic()
        wait = interval - (now - _last_mtop_at)
        _last_mtop_at = now if wait <= 0 else now + wait
    if wait > 0:
        time.sleep(wait)


def _classify_error(ret0: str) -> str:
    u = ret0.upper()
    if "FAIL_SYS_USER_VALIDATE" in u or "X5SEC" in u:
        return "validate"
    if "RGV587" in u or "挤爆" in ret0:
        return "rgv587"
    if "SESSION" in u or "TOKEN" in u:
        return "session"
    return "network"


def _report_broker(
    session: Session,
    *,
    api: str,
    ret: list[str],
    error_kind: str,
    message: str,
    set_cookies: list[str],
    duration_ms: int,
    ok: bool,
) -> None:
    if not session.from_broker:
        return
    try:
        from xianyu_radar.auth.broker_client import get_broker_client

        get_broker_client().report(
            api=api,
            ret=ret,
            error_kind=error_kind,
            message=message,
            set_cookies=set_cookies,
            duration_ms=duration_ms,
            ok=ok,
            lease_id=session.lease_id or None,
        )
    except Exception:
        return


def call_mtop(
    session: Session,
    api_name: str,
    data: dict[str, Any],
    extra_params: dict[str, str] | None = None,
    *,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
    headers_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Call mtop.{api_name}. api_name should be without leading 'mtop.'
    e.g. 'idle.web.xyh.item.list' or 'taobao.idlemtopsearch.pc.search'
    """
    if not session.ok:
        raise AuthError("Session incomplete")

    kind = _api_kind(api_name)
    _global_pace(kind, session)

    ts = str(int(time.time() * 1000))
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
    if session.headers:
        headers.update(session.headers)
        headers["Cookie"] = session.cookies  # never let lease headers override Cookie
    if headers_extra:
        headers.update(headers_extra)
        headers["Cookie"] = session.cookies

    owns_client = client is None
    if owns_client:
        proxy = os.environ.get("RADAR_HTTP_PROXY") or os.environ.get("RADAR_HTTPS_PROXY")
        client = httpx.Client(timeout=timeout, trust_env=False, proxy=proxy or None)

    started = time.monotonic()
    set_cookies: list[str] = []
    try:
        resp = client.post(url, content=body, headers=headers)
        set_cookies = resp.headers.get_list("set-cookie")
        text = resp.text
        match = JSONP_RE.match(text)
        parsed = json.loads(match.group(1) if match else text)
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        _report_broker(
            session,
            api=api_name,
            ret=[],
            error_kind="network",
            message=str(e),
            set_cookies=set_cookies,
            duration_ms=duration_ms,
            ok=False,
        )
        raise MtopError(f"MTOP request failed: {e}") from e
    finally:
        if owns_client:
            client.close()

    duration_ms = int((time.monotonic() - started) * 1000)
    ret = parsed.get("ret") or []
    ret_list = [str(x) for x in ret] if isinstance(ret, list) else [str(ret)]
    ret0 = ret_list[0] if ret_list else ""

    if isinstance(ret0, str) and ret0.startswith("SUCCESS"):
        _report_broker(
            session,
            api=api_name,
            ret=ret_list,
            error_kind="none",
            message="",
            set_cookies=set_cookies,
            duration_ms=duration_ms,
            ok=True,
        )
        return parsed

    kind_err = _classify_error(ret0 if isinstance(ret0, str) else "")
    _report_broker(
        session,
        api=api_name,
        ret=ret_list,
        error_kind=kind_err,
        message=str(ret0),
        set_cookies=set_cookies,
        duration_ms=duration_ms,
        ok=False,
    )
    if kind_err == "validate":
        raise MtopError("x5sec / USER_VALIDATE required", ret=ret, payload=parsed)
    if kind_err == "session":
        raise AuthError(f"Auth failed: {ret0}")
    if kind_err == "rgv587":
        raise MtopError(f"rate limited: {ret}", ret=ret, payload=parsed)
    raise MtopError(f"MTOP error: {ret}", ret=ret, payload=parsed)

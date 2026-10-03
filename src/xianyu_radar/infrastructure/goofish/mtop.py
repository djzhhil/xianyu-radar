"""MTOP executor: scoped signing, every-hop updates and bounded token retry."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

from xianyu_radar.config import MTOP_APP_KEY, MTOP_BASE
from xianyu_radar.infrastructure.goofish.cookie_jar import allowed_url, clean_url
from xianyu_radar.infrastructure.goofish.errors import AuthError, HelperError, error_kind
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.helper.client import validate_updates

JSONP_RE = re.compile(r"^\s*mtopjsonp\d+\s*\((.*)\)\s*;?\s*$", re.DOTALL)
READ_ONLY_APIS = frozenset({"taobao.idlemtopsearch.pc.search", "taobao.idle.pc.detail", "idle.web.xyh.item.list"})


class MtopError(Exception):
    def __init__(self, message: str, *, ret: Any = None, payload: Any = None, kind: str | None = None):
        super().__init__(message)
        self.ret, self.payload, self.kind = ret, payload, kind


def make_mtop_client(*, timeout: float = 20.0) -> httpx.Client:
    proxy = os.environ.get("RADAR_HTTP_PROXY") or os.environ.get("RADAR_HTTPS_PROXY")
    return httpx.Client(timeout=timeout, trust_env=False, proxy=proxy or None, follow_redirects=False)


def create_sign(token: str, ts: str | int, data_str: str, app_key: str = MTOP_APP_KEY) -> str:
    return hashlib.md5(f"{token}&{ts}&{app_key}&{data_str}".encode()).hexdigest()


def _page(extra: dict | None) -> str:
    spm = (extra or {}).get("spm_cnt", "")
    path = "personal" if ".personal." in spm else "item" if ".item." in spm else "search"
    return f"https://www.goofish.com/{path}"


def _submit(session: Session, batches: list[dict]) -> None:
    if not batches:
        return
    try:
        validate_updates(session.credential_version, batches)
        result = session.submit_updates(batches)
        session.credential_version = result["credential_version"]
    except Exception as exc:
        session.invalidate(error_kind(exc))
        raise
    finally:
        batches.clear()


def _exchange(session: Session, client: httpx.Client, url: str, body: str, page: str) -> tuple[int, str]:
    batches = []
    visited = set()
    method = "POST"
    try:
        for hop in range(6):
            if not allowed_url(url) or url in visited:
                raise MtopError("闲鱼重定向来源无效或发生循环。", kind="network")
            visited.add(url)
            headers = {
                "Cookie": session.jar.header(url), "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www.goofish.com", "Referer": page,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json", "Accept-Language": "zh-CN,zh;q=0.9",
            }
            # Streaming captures headers before body consumption. Body failure
            # must still submit the updates already received on this hop.
            with client.stream(method, url, content=body if method == "POST" else None,
                               headers=headers, follow_redirects=False) as response:
                received = datetime.now(timezone.utc)
                updates = response.headers.get_list("set-cookie")
                if updates:
                    batch = {"response_url": clean_url(str(response.request.url)),
                             "received_at": received.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                             "set_cookies": updates}
                    batches.append(batch)
                    validate_updates(session.credential_version, batches)
                    session.jar.apply(batch["response_url"], updates, received)
                response.read()
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = urljoin(url, response.headers.get("location", ""))
                    if not response.headers.get("location") or not allowed_url(target) or hop == 5:
                        raise MtopError("闲鱼重定向目标无效或超过五跳。", kind="network")
                    if response.status_code in {301, 302, 303}:
                        method = "GET"
                    url = target
                    continue
                return response.status_code, response.text
    except httpx.HTTPError:
        raise MtopError("闲鱼请求或响应读取失败。", kind="network") from None
    finally:
        # Runs before HTTP/business/body parsing and even on invalid redirects.
        _submit(session, batches)
    raise MtopError("闲鱼重定向未完成。", kind="network")


def _classify(ret: list) -> str:
    blob = " ".join(str(x).upper() for x in ret)
    if "USER_VALIDATE" in blob:
        return "verification_required"
    if any(code in blob for code in ("RGV587", "LIMIT", "FREQUENCY", "TRAFFIC")):
        return "rate_limit"
    if any(code in blob for code in ("SESSION_EXPIRED", "SID_INVALID", "NEED_LOGIN", "SESSION_INVALID", "USER_NOT_LOGIN")):
        return "auth"
    if any(code in blob for code in ("TOKEN_EMPTY", "TOKEN_EXPIRED", "TOKEN_EXOIRED")):
        return "token"
    return "platform"


def call_mtop(session: Session, api_name: str, data: dict[str, Any],
              extra_params: dict[str, str] | None = None, *, timeout: float = 20.0,
              client: httpx.Client | None = None) -> dict[str, Any]:
    session.ensure_online()
    owns = client is None
    client = make_mtop_client(timeout=timeout) if owns else client
    page = _page(extra_params)
    try:
        for attempt in range(2):
            token = session.jar.token(page)
            if not token:
                raise MtopError("Helper 快照缺少页面可见签名 Token，请在 Helper 恢复登录态。", kind="token")
            ts = str(int(time.time() * 1000))
            data_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            params = {"jsv": "2.7.2", "appKey": MTOP_APP_KEY, "t": ts,
                      "sign": create_sign(token, ts, data_str), "v": "1.0",
                      "type": "originaljson", "api": f"mtop.{api_name}", "dataType": "json",
                      "timeout": "20000", "accountSite": "xianyu", "sessionOption": "AutoLoginOnly"}
            if extra_params:
                params.update({k: str(v) for k, v in extra_params.items()})
            url = f"{MTOP_BASE}/mtop.{api_name}/1.0/?{urlencode(params)}"
            status, text = _exchange(session, client, url, urlencode({"data": data_str}), page)
            if status == 429:
                raise MtopError("闲鱼限流，请稍后重试。", kind="rate_limit")
            try:
                match = JSONP_RE.match(text)
                parsed = json.loads(match.group(1) if match else text)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("ret"), list):
                    raise ValueError("shape")
            except (ValueError, TypeError):
                raise MtopError("闲鱼响应无法解析。", kind="parse_failed") from None
            ret = parsed["ret"]
            kind = _classify(ret)
            # Error classification precedes success; a mixed ret cannot conceal
            # verification/session failure. Never include arbitrary ret in logs.
            if (kind == "token" and api_name in READ_ONLY_APIS and 200 <= status < 300
                    and attempt == 0 and session.jar.token(page) not in ("", token)):
                continue
            if kind == "auth":
                raise AuthError("闲鱼登录态已失效，请在 Helper 重新登录并检查。")
            if kind in {"verification_required", "rate_limit", "token"}:
                message = {"verification_required": "闲鱼要求人机验证，请在 Helper 完成验证。",
                           "rate_limit": "闲鱼限流，请稍后重试。", "token": "签名 Token 恢复失败，请在 Helper 检查登录态。"}[kind]
                raise MtopError(message, kind=kind)
            if not 200 <= status < 300:
                raise MtopError("闲鱼 HTTP 状态异常。", kind="http")
            if ret and isinstance(ret[0], str) and ret[0].startswith("SUCCESS"):
                return parsed
            raise MtopError("闲鱼业务接口返回失败。", kind="platform")
    except (MtopError, AuthError, HelperError) as exc:
        session.invalidate(error_kind(exc))
        raise
    finally:
        # httpx's own Jar must never survive or override our scoped session.
        client.cookies.clear()
        if owns:
            client.close()
    raise MtopError("Token 重试次数已耗尽。", kind="token")

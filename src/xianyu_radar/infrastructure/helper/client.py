"""Helper's authenticated snapshot/update contract; never proxies MTOP."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx

from xianyu_radar.infrastructure.goofish.cookie_jar import CookieJar, allowed_url
from xianyu_radar.infrastructure.goofish.errors import HelperError


@dataclass(frozen=True)
class HelperConfig:
    base_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    account_id: str

    @classmethod
    def from_env(cls) -> HelperConfig:
        values = [os.environ.get("RADAR_HELPER_" + key, "") for key in
                  ("BASE_URL", "USERNAME", "PASSWORD", "ACCOUNT_ID")]
        if not all(values):
            raise HelperError("helper_config", "请配置 Helper 地址、登录凭据和目标账号。")
        config = cls(*values)
        try:
            u = urlsplit(config.base_url)
            valid = (u.hostname and u.port != 0 and u.username is None and u.password is None
                     and not u.query and not u.fragment and u.path in ("", "/")
                     and (u.scheme == "https" or (u.scheme == "http" and u.hostname in {"localhost", "127.0.0.1", "::1"})))
        except ValueError:
            valid = False
        if not valid:
            raise HelperError("helper_config", "Helper 地址需为 HTTPS，或受控回环 HTTP 地址。")
        return config


class HelperClient:
    def __init__(self, config: HelperConfig, *, transport: httpx.BaseTransport | None = None):
        self.config = config
        # No environment/MTOP proxy, no redirects, no shared cookie container.
        self.http = httpx.Client(base_url=config.base_url.rstrip("/"), timeout=10,
                                 trust_env=False, follow_redirects=False, transport=transport)
        self.authenticated = False

    def close(self) -> None:
        self.http.cookies.clear()
        self.http.close()

    def _login(self) -> None:
        self.http.cookies.clear()
        try:
            response = self.http.post("/api/v1/session/login", json={
                "username": self.config.username, "password": self.config.password,
            })
        except httpx.HTTPError:
            raise HelperError("helper_unavailable", "Helper 连接失败，请检查服务和网络。") from None
        if response.status_code != 200:
            if response.status_code in (401, 403):
                raise HelperError("helper_auth", "Helper 登录失败，请检查服务端登录配置。")
            self._failure(response.status_code, update=False)
        if not self.http.cookies:
            raise HelperError("helper_contract", "Helper 登录未建立管理会话。")
        self.authenticated = True

    @staticmethod
    def _failure(status: int, *, update: bool, code: str | None = None) -> None:
        if status == 401:
            raise HelperError("helper_auth", "Helper 认证失败，请检查登录配置。")
        if status == 403:
            raise HelperError("helper_permission", "Helper 用户无权访问配置的账号。", status=403)
        if status == 404:
            raise HelperError("helper_account", "Helper 账号或交换接口不存在，请检查配置。", status=404)
        if status == 409:
            kind = "cookie_snapshot_unavailable" if code == "cookie_snapshot_unavailable" or not update else "credential_conflict"
            message = "Helper 凭证版本冲突；当前操作停止，请重新开始或继续进度。" if kind == "credential_conflict" else "Helper 没有完整 Cookie 快照，请先在 Helper 登录。"
            raise HelperError(kind, message, status=409)
        if update and (status >= 500 or 300 <= status < 400):
            raise HelperError("cookie_update_unknown", "Cookie 回写结果未知；当前操作停止，请重新获取 Helper 状态。")
        if update:
            raise HelperError("cookie_update_rejected", "Helper 拒绝 Cookie 更新；当前操作停止。", status=502)
        raise HelperError("helper_unavailable", "Helper 服务或接口异常，在线操作已停止。")

    def _request(self, method: str, path: str, *, payload: dict | None = None) -> dict:
        update = method == "POST"
        if not self.authenticated:
            self._login()
        for attempt in range(2):
            try:
                response = self.http.request(method, path, json=payload) if payload is not None else self.http.request(method, path)
            except httpx.HTTPError:
                kind = "cookie_update_unknown" if update else "helper_unavailable"
                raise HelperError(kind, "Cookie 回写结果未知；当前操作停止。" if update else "Helper 不可达；在线操作停止。") from None
            if response.status_code == 401 and attempt == 0:
                self._login()
                continue
            if response.status_code != 200:
                try:
                    envelope = response.json()
                    code = envelope.get("code") if isinstance(envelope, dict) else None
                except ValueError:
                    code = None
                # Only known machine codes affect behavior; never expose the
                # remote message/details which may contain credentials.
                self._failure(response.status_code, update=update, code=code)
            try:
                data = response.json()
            except (ValueError, UnicodeError):
                data = None
            if not isinstance(data, dict):
                raise HelperError("cookie_update_unknown" if update else "helper_contract", "Helper 返回了无效契约响应，当前操作停止。")
            return data
        raise AssertionError("bounded authentication loop")

    def _path(self, suffix: str) -> str:
        return f"/api/v1/integrations/accounts/{quote(self.config.account_id, safe='')}/{suffix}"

    def snapshot(self) -> tuple[CookieJar, str]:
        data = self._request("GET", self._path("cookie-snapshot"))
        if (data.get("account_id") != self.config.account_id or data.get("snapshot_complete") is not True
                or not isinstance(data.get("credential_version"), str) or not data["credential_version"]
                or not isinstance(data.get("cookies"), list) or not data["cookies"]):
            raise HelperError("helper_contract", "Helper 未返回有效完整快照；请在 Helper 检查账号。")
        try:
            jar = CookieJar(data["cookies"])
        except ValueError:
            raise HelperError("helper_contract", "Helper Cookie 快照属性不符合契约。") from None
        return jar, data["credential_version"]

    def updates(self, version: str, batches: list[dict]) -> dict:
        payload = validate_updates(version, batches)
        data = self._request("POST", self._path("cookie-updates"), payload=payload)
        if (data.get("account_id") != self.config.account_id or not isinstance(data.get("changed"), bool)
                or not isinstance(data.get("credential_version"), str) or not data["credential_version"]
                or data.get("runtime_sync_status") not in {"synced", "not_running", "not_needed", "failed"}):
            raise HelperError("cookie_update_unknown", "Cookie 回写响应无效，结果未知；当前操作停止。")
        return data


def validate_updates(version: str, batches: list[dict]) -> dict:
    if not 1 <= len(batches) <= 32:
        raise HelperError("cookie_update_limit", "Cookie 更新批次数超出 Helper 契约限制。")
    now = datetime.now(timezone.utc)
    for batch in batches:
        headers = batch["set_cookies"]
        received = datetime.fromisoformat(batch["received_at"].replace("Z", "+00:00"))
        age = (now - received).total_seconds()
        if (not allowed_url(batch["response_url"]) or not 1 <= len(headers) <= 128
                or any(len(h.encode()) > 8192 for h in headers) or not -30 <= age <= 600):
            raise HelperError("cookie_update_limit", "Cookie 更新来源、体积或时间超出 Helper 契约限制。")
    payload = {"credential_version": version, "responses": batches}
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()) > 256 * 1024:
        raise HelperError("cookie_update_limit", "Cookie 更新体积超出 Helper 契约限制。")
    return payload

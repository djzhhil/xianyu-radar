"""Short-lived online session; legacy parsing is explicit and offline only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from xianyu_radar.infrastructure.goofish.cookie_jar import CookieJar
from xianyu_radar.infrastructure.goofish.errors import AuthError, HelperError


@dataclass
class Session:
    # The first fields preserve the offline business fixture constructor. MTOP
    # refuses these flat fixtures: production requires the Helper submit port.
    cookies: str = field(default="", repr=False)
    token: str = field(default="", repr=False)
    source: str = "offline"
    cookie_count: int = 0
    jar: CookieJar | None = field(default=None, repr=False)
    credential_version: str = field(default="", repr=False)
    account_id: str = ""
    submit_updates: Callable | None = field(default=None, repr=False)
    closed: bool = False
    stop_kind: str | None = None

    @property
    def ok(self) -> bool:
        return not self.closed and (self.jar is not None or bool(self.cookies and self.token))

    @property
    def looks_like_placeholder(self) -> bool:
        return self.jar is None and (self.token.lower() in {"tokensecret", "hello", "token", "test", "abc"} or self.token.startswith("dummy"))

    def ensure_online(self) -> None:
        if self.closed or self.stop_kind:
            raise HelperError(self.stop_kind or "helper_contract", "当前临时会话已停止，请重新获取 Helper 状态。")
        if self.jar is None or self.submit_updates is None or self.source != "Helper":
            raise HelperError("helper_config", "在线请求只接受 Helper 临时会话，不支持本地 Cookie。")

    def invalidate(self, kind: str) -> None:
        self.stop_kind = kind
        if self.jar is not None:
            self.jar.cookies.clear()

    def close(self) -> None:
        if self.jar is not None:
            self.jar.cookies.clear()
        self.cookies = self.token = self.credential_version = ""
        self.submit_updates = None
        self.closed = True


def parse_offline_session(raw: dict) -> Session:
    """Parse synthetic fixtures only; no filesystem or default-state lookup."""
    cookies = raw.get("cookies", raw.get("cookie", ""))
    if isinstance(cookies, list):
        pairs = [(c.get("name"), c.get("value")) for c in cookies if isinstance(c, dict)]
        cookies = "; ".join(f"{name}={value}" for name, value in pairs if name and value is not None)
    if not isinstance(cookies, str):
        raise AuthError("无效离线夹具")
    parts = [p.strip() for p in cookies.split(";") if p.strip()]
    token = next((p.split("=", 1)[1].split("_", 1)[0] for p in parts if p.startswith("_m_h5_tk=")), "")
    if not token:
        raise AuthError("离线夹具缺少签名 Token")
    return Session(cookies, token, "offline", len(parts))

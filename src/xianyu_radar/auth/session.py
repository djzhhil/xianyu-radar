"""Auth session loading from state JSON files or Helper Session Broker."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from xianyu_radar import config as cfg


class AuthError(Exception):
    """Login / session problems."""


@dataclass
class Session:
    cookies: str
    token: str
    source: str
    cookie_count: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    lease_id: str = ""
    account_id: str = ""
    quotas_ms: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.cookies and self.token)

    @property
    def from_broker(self) -> bool:
        return self.source.startswith("broker:")

    @property
    def looks_like_placeholder(self) -> bool:
        """True for unit-test / docs sample tokens that cannot call goofish."""
        t = (self.token or "").lower()
        return t in {"tokensecret", "hello", "token", "test", "abc"} or t.startswith("dummy")


def auth_mode() -> str:
    """Return 'broker' or 'local'."""
    raw = (os.environ.get("RADAR_AUTH_MODE") or cfg.AUTH_MODE or "local").strip().lower()
    if raw == "broker":
        return "broker"
    # Auto: broker when env fully configured
    if raw == "auto":
        from xianyu_radar.auth.broker_client import get_broker_client

        return "broker" if get_broker_client().configured else "local"
    return "local"


def _cookies_from_list(cookies: list) -> tuple[str, str, int]:
    """Build cookie header and extract _m_h5_tk token from cookie list."""
    pairs: list[str] = []
    token = ""
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = c.get("name") or c.get("Name")
        value = c.get("value") if "value" in c else c.get("Value")
        if not name or value is None:
            continue
        pairs.append(f"{name}={value}")
        if name == "_m_h5_tk":
            token = str(value).split("_", 1)[0]
    return "; ".join(pairs), token, len(pairs)


def _cookies_from_header(cookie_header: str) -> tuple[str, str, int]:
    token = ""
    parts = [p.strip() for p in cookie_header.split(";") if p.strip()]
    for part in parts:
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        if name.strip() == "_m_h5_tk":
            token = value.strip().split("_", 1)[0]
    return cookie_header.strip(), token, len(parts)


def load_session_local(path: Path | str | None = None) -> Session:
    """
    Load session from JSON. Supported shapes:

    1) { "cookies": [ { "name", "value", ... }, ... ] }
    2) Asher-style snapshot with top-level "cookies" array (+ optional env/headers)
    3) { "cookie": "a=1; b=2; _m_h5_tk=xxx_ts" }
    4) { "cookies": "a=1; b=2" }
    """
    if path is None:
        default = cfg.STATE_DIR / "default.json"
        if default.exists():
            path = default
        else:
            candidates = sorted(cfg.STATE_DIR.glob("*.json"))
            if not candidates:
                raise AuthError(
                    f"No session file found under {cfg.STATE_DIR}. "
                    "Place a cookie JSON at data/<env>/state/default.json "
                    "or set RADAR_AUTH_MODE=broker"
                )
            path = candidates[0]
    path = Path(path)
    if not path.exists():
        raise AuthError(f"Session file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AuthError("Session JSON must be an object")

    if isinstance(raw.get("cookies"), list):
        cookie_str, token, count = _cookies_from_list(raw["cookies"])
    elif isinstance(raw.get("cookies"), str):
        cookie_str, token, count = _cookies_from_header(raw["cookies"])
    elif isinstance(raw.get("cookie"), str):
        cookie_str, token, count = _cookies_from_header(raw["cookie"])
    else:
        raise AuthError(
            "Unsupported session format. Need cookies list or cookie header string."
        )

    if not token:
        raise AuthError("Missing _m_h5_tk cookie (required for MTOP sign)")

    return Session(
        cookies=cookie_str,
        token=token,
        source=str(path),
        cookie_count=count,
    )


def load_session(path: Path | str | None = None) -> Session:
    """Load from broker when configured, otherwise local JSON."""
    mode = auth_mode()
    if mode == "broker" and path is None:
        from xianyu_radar.auth.broker_client import BrokerError, get_broker_client

        try:
            return get_broker_client().ensure_session()
        except BrokerError as e:
            raise AuthError(str(e)) from e
    return load_session_local(path)


def try_load_session(path: Path | str | None = None) -> Session | None:
    try:
        return load_session(path)
    except AuthError:
        return None

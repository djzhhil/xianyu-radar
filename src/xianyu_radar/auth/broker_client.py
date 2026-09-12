"""HTTP client for Helper Session Broker."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from xianyu_radar.auth.session import AuthError, Session


class BrokerError(Exception):
    """Broker transport / protocol errors."""


@dataclass
class Lease:
    lease_id: str
    cookie_id: str
    cookies: str
    device_id: str = ""
    etag: str = ""
    expires_at: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    quotas_ms: dict[str, int] = field(default_factory=dict)
    health: str = "ok"

    @property
    def expired(self) -> bool:
        return self.expires_at > 0 and time.time() >= (self.expires_at - 30)


class BrokerClient:
    """Lease cookies from Helper and report MTOP outcomes."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        account_id: str | None = None,
        *,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("RADAR_BROKER_URL") or "").rstrip("/")
        self.token = token or os.environ.get("RADAR_BROKER_TOKEN") or ""
        self.account_id = account_id or os.environ.get("RADAR_ACCOUNT_ID") or ""
        self.timeout = timeout
        self._lease: Lease | None = None
        self._lock = threading.Lock()
        self._last_call_at: dict[str, float] = {}

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token and self.account_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.configured:
            raise BrokerError("Broker not configured (RADAR_BROKER_URL/TOKEN/ACCOUNT_ID)")
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False) as client:
                resp = client.request(method, url, headers=self._headers(), **kwargs)
        except Exception as e:
            raise BrokerError(f"broker request failed: {e}") from e
        if resp.status_code >= 400:
            from xianyu_radar.security import redact_secrets

            raise BrokerError(
                redact_secrets(f"broker HTTP {resp.status_code}: {resp.text[:200]}")
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise BrokerError("broker returned non-object JSON")
        return data

    def list_accounts(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/v1/session-broker/accounts")
        accounts = data.get("accounts") or []
        return accounts if isinstance(accounts, list) else []

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/session-broker/health")

    def lease(self, *, force: bool = False) -> Lease:
        with self._lock:
            if not force and self._lease and not self._lease.expired:
                return self._lease
            data = self._request(
                "POST",
                f"/api/v1/session-broker/accounts/{self.account_id}/lease",
                json={"consumer": "radar"},
            )
            lease = Lease(
                lease_id=str(data.get("lease_id") or ""),
                cookie_id=str(data.get("cookie_id") or self.account_id),
                cookies=str(data.get("cookies") or ""),
                device_id=str(data.get("device_id") or ""),
                etag=str(data.get("etag") or ""),
                expires_at=int(data.get("expires_at") or 0),
                headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
                quotas_ms={str(k): int(v) for k, v in (data.get("quotas_ms") or {}).items()},
                health=str(data.get("health") or "ok"),
            )
            if not lease.cookies or not lease.lease_id:
                raise BrokerError("lease response missing cookies/lease_id")
            self._lease = lease
            return lease

    def ensure_session(self) -> Session:
        lease = self.lease()
        token = ""
        for part in lease.cookies.split(";"):
            part = part.strip()
            if part.startswith("_m_h5_tk="):
                token = part.split("=", 1)[1].split("_", 1)[0]
                break
        if not token:
            raise AuthError("Broker lease missing _m_h5_tk")
        count = len([p for p in lease.cookies.split(";") if "=" in p])
        return Session(
            cookies=lease.cookies,
            token=token,
            source=f"broker:{lease.cookie_id}:{lease.lease_id}",
            cookie_count=count,
            headers=dict(lease.headers),
            lease_id=lease.lease_id,
            account_id=lease.cookie_id,
            quotas_ms=dict(lease.quotas_ms),
        )

    def report(
        self,
        *,
        api: str,
        ret: list[str] | None = None,
        error_kind: str = "none",
        message: str = "",
        set_cookies: list[str] | None = None,
        duration_ms: int = 0,
        ok: bool = False,
        lease_id: str | None = None,
    ) -> None:
        lease = self._lease
        cid = self.account_id
        lid = lease_id or (lease.lease_id if lease else "")
        try:
            self._request(
                "POST",
                f"/api/v1/session-broker/accounts/{cid}/report",
                json={
                    "lease_id": lid,
                    "consumer": "radar",
                    "api": api,
                    "ret": ret or [],
                    "error_kind": error_kind,
                    "message": message,
                    "set_cookies": set_cookies or [],
                    "duration_ms": duration_ms,
                    "ok": ok,
                },
            )
        except BrokerError:
            # Reporting must not break scanning path.
            return
        if error_kind in {"validate", "rgv587", "session"} and lease:
            with self._lock:
                self._lease = None

    def pace(self, kind: str = "list") -> None:
        """Sleep according to broker quotas (or defaults)."""
        lease = self._lease
        defaults = {"list": 1000, "search": 2000, "detail": 2500}
        ms = defaults.get(kind, 1000)
        if lease and lease.quotas_ms.get(kind):
            ms = int(lease.quotas_ms[kind])
        now = time.monotonic()
        with self._lock:
            last = self._last_call_at.get(kind, 0.0)
            wait = (ms / 1000.0) - (now - last)
            self._last_call_at[kind] = now if wait <= 0 else now + wait
        if wait > 0:
            time.sleep(wait)


_client: BrokerClient | None = None
_client_lock = threading.Lock()


def get_broker_client() -> BrokerClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = BrokerClient()
        return _client


def reset_broker_client() -> None:
    global _client
    with _client_lock:
        _client = None

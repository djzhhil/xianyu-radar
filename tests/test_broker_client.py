"""Tests for broker client helpers and session modes."""

from __future__ import annotations

import os

import pytest

from xianyu_radar.auth.broker_client import BrokerClient, Lease
from xianyu_radar.auth.session import Session, auth_mode


def test_lease_expired():
    lease = Lease(lease_id="l1", cookie_id="c1", cookies="a=1", expires_at=1)
    assert lease.expired is True


def test_auth_mode_local(monkeypatch):
    monkeypatch.setenv("RADAR_AUTH_MODE", "local")
    monkeypatch.delenv("RADAR_BROKER_URL", raising=False)
    assert auth_mode() == "local"


def test_session_from_broker_flag():
    s = Session(cookies="a=1", token="tok", source="broker:cid:lease", cookie_count=1)
    assert s.from_broker is True
    assert s.ok


def test_broker_client_not_configured(monkeypatch):
    monkeypatch.delenv("RADAR_BROKER_URL", raising=False)
    monkeypatch.delenv("RADAR_BROKER_TOKEN", raising=False)
    monkeypatch.delenv("RADAR_ACCOUNT_ID", raising=False)
    c = BrokerClient(base_url="", token="", account_id="")
    assert c.configured is False

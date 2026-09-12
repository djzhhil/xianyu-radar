"""API integration tests with TestClient."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from xianyu_radar.api.app import create_app
from xianyu_radar import config as cfg

REAL_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Isolate ROOT_DIR under tmp; keep fixtures/web via symlink."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "fixtures").symlink_to(REAL_ROOT / "tests" / "fixtures")
    (tmp_path / "web").symlink_to(REAL_ROOT / "web")
    monkeypatch.setattr(cfg, "ROOT_DIR", tmp_path)
    monkeypatch.delenv("RADAR_ENV", raising=False)
    app = create_app("prod")
    return TestClient(app)


def test_health_and_index(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json().get("env") == "prod"
    page = client.get("/")
    assert page.status_code == 200
    assert b"xianyu-radar" in page.content


def test_offline_demo_loop_and_candidates(client: TestClient) -> None:
    r = client.post("/api/demo/offline-loop", json={"keyword": "Sony A7M4", "seller_id": "DEMO"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["env"] == "demo"
    assert body["second_scan"]["candidates"]["added"] >= 1

    # Demo writes demo DB; switch UI env so status/candidates read it.
    sw = client.post("/api/env", json={"env": "demo"})
    assert sw.status_code == 200
    assert sw.json()["env"] == "demo"

    status = client.get("/api/status").json()
    assert status["env"] == "demo"
    assert status["counts"]["candidates"] >= 1

    cands = client.get("/api/candidates?since=24h").json()
    assert cands["count"] >= 1
    assert any("Photoshop" in (c.get("sample_title") or "") for c in cands["candidates"])

    events = client.get("/api/events?since=24h").json()
    assert events["count"] >= 1


def test_discover_fixture(client: TestClient) -> None:
    r = client.post(
        "/api/discover",
        json={
            "keyword": "Sony A7M4",
            "fixture": "tests/fixtures/search_results.json",
            "no_enrich": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["item_count"] == 1


def test_save_session(client: TestClient) -> None:
    r = client.post(
        "/api/auth/session",
        json={
            "payload": {"cookie": "_m_h5_tk=tokensecret_1710000000000; a=1"},
            "filename": "default.json",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json().get("looks_like_placeholder") is True
    auth = client.get("/api/auth/status").json()
    assert auth["ok"] is True
    assert auth.get("looks_like_placeholder") is True


def test_env_switch(client: TestClient) -> None:
    r = client.get("/api/env")
    assert r.status_code == 200
    assert r.json()["env"] == "prod"
    r2 = client.post("/api/env", json={"env": "demo"})
    assert r2.status_code == 200
    assert r2.json()["env"] == "demo"
    assert client.get("/api/status").json()["env"] == "demo"

"""Business progress and public-entry regressions for Helper-only sessions."""
from contextlib import contextmanager
import json
from urllib.parse import parse_qs
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from xianyu_radar import config as cfg
from xianyu_radar.entrypoints.api import deps
from xianyu_radar.entrypoints.cli import main
from xianyu_radar.infrastructure.goofish.errors import HelperError
from xianyu_radar.infrastructure.goofish.cookie_jar import CookieJar
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery
from xianyu_radar.modules.discovery.service import discover_sellers, get_discovery_run
from xianyu_radar.modules.scan import runner
from xianyu_radar.modules.scan.service import scan_seller
from xianyu_radar.modules.auth import service as auth_service

FIXTURES = Path(__file__).parent / "fixtures"


def online(submit):
    return Session(source="Helper", jar=CookieJar([
        {"name":"_m_h5_tk","value":"synthetic_1","domain":".goofish.com","path":"/","secure":True},
    ]), credential_version="v1:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", account_id="fixture", submit_updates=submit)


def success(batches):
    return {"credential_version":"v1:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "runtime_sync_status":"not_needed", "changed":False}


@pytest.mark.parametrize("kind", ["credential_conflict", "cookie_update_unknown"])
def test_discovery_preserves_confirmed_page_and_resume_without_duplicate_seller(monkeypatch, tmp_path, kind):
    from xianyu_radar.infrastructure.goofish import mtop
    conn = init_db(tmp_path / "business.sqlite3")
    first = json.loads((FIXTURES / "search_results.json").read_text())
    first["ret"] = ["SUCCESS"]
    first["data"]["nextPage"] = 2
    first["data"]["resultList"][0]["data"]["item"]["main"]["clickParam"]["args"]["seller_id"] = "998877"
    pages = []
    def handler(req):
        page = json.loads(parse_qs(req.content.decode())["data"][0])["pageNumber"]
        pages.append(page)
        return httpx.Response(200, json=first if page == 1 else {"ret":["SUCCESS"], "data":{"resultList":[], "nextPage":False}},
                              headers={} if page == 1 else {"set-cookie":"a=synthetic; Path=/"})
    def reject(batches):
        raise HelperError(kind, "synthetic helper failure")
    monkeypatch.setattr(mtop, "make_mtop_client", lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler)))
    s = online(reject)
    result = discover_sellers(conn, "fixture", session=s, enrich=True, rows_per_page=1)
    assert result["error_kind"] == kind and result["new_sellers"] == 1
    assert pages == [1, 2] and s.stop_kind == kind
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    run = get_discovery_run(conn, result["run_id"])
    assert run["run"]["status"] != "ok"
    pages.clear()
    resumed = discover_sellers(conn, "fixture", session=online(success), enrich=False, rows_per_page=1,
                               resume_run_id=result["run_id"])
    assert pages == [2] and resumed["status"] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM seller_pool_entries").fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize("kind", ["credential_conflict", "cookie_update_unknown", "helper_unavailable"])
def test_scan_does_not_write_unconfirmed_catalog_or_continue_pool(monkeypatch, tmp_path, kind):
    conn = init_db(tmp_path / "business.sqlite3")
    for seller in ("111", "222"):
        add_seller_from_discovery(conn, seller_id=seller, nickname="fixture", source_keyword="fixture", source_item_id=None)
    conn.commit()
    calls = []
    def fail(*args, **kwargs):
        calls.append(args[1])
        raise HelperError(kind, "synthetic failure")
    monkeypatch.setattr("xianyu_radar.modules.scan.service.get_seller_items", fail)
    result = runner.run_pool_once(conn, online(success), between_sellers_sec=0, jitter_sec=0)
    assert calls == ["111"] and len(result) == 1 and result[0]["error_kind"] == kind
    assert conn.execute("SELECT COUNT(*) FROM item_events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM item_snapshots").fetchone()[0] == 0
    assert conn.execute("SELECT SUM(consecutive_failures) FROM sellers").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize("command", [
    ["auth","check"], ["search","-k","fixture"], ["discover","-k","fixture"],
    ["fetch-seller","111"], ["scan-seller","111"], ["scan-pool"], ["run"],
])
def test_every_online_cli_rejects_state_before_database_or_network(monkeypatch, command, capsys):
    monkeypatch.setattr("xianyu_radar.entrypoints.cli._conn", lambda: pytest.fail("must reject before opening database"))
    with pytest.raises(SystemExit) as error:
        main(command + ["--state", "/synthetic/old.json"])
    assert error.value.code == 2
    assert "--state 已废弃" in capsys.readouterr().err


def test_public_api_no_cookie_fallback_or_user_account_override(monkeypatch, tmp_path):
    from xianyu_radar.entrypoints.api.app import create_app
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cfg, "DEBUG_DIR", tmp_path / "debug")
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "business.sqlite3")
    old = tmp_path / "state/default.json"
    old.parent.mkdir()
    old.write_text('{"cookie":"synthetic-old-cookie"}')
    for key in ("BASE_URL", "USERNAME", "PASSWORD", "ACCOUNT_ID"):
        monkeypatch.delenv("RADAR_HELPER_" + key, raising=False)
    monkeypatch.setattr(runner, "run_loop", lambda *args, **kwargs: pytest.fail("Web must not launch scanning"))
    with TestClient(create_app()) as client:
        assert client.post("/api/auth/session", json={"payload":{"cookie":"synthetic-new-cookie"}}).status_code == 410
        for path, body in [("/api/auth/check",None), ("/api/discover",{"keyword":"fixture"}),
                           ("/api/scan/seller/111",None), ("/api/scan/pool",None)]:
            response = client.post(path, json=body)
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "helper_config"
            assert "synthetic-old-cookie" not in response.text
        assert client.get("/api/items/123/detail").status_code == 503
        assert client.post("/api/discover", json={"keyword":"fixture","account_id":"other"}).status_code == 422
        assert client.get("/api/status").status_code == 200
        assert client.get("/api/pool").status_code == 200
        assert client.get("/api/candidates").status_code == 200
    assert old.read_text() == '{"cookie":"synthetic-old-cookie"}'


def test_clear_pause_requires_fresh_online_success(monkeypatch, tmp_path):
    conn = init_db(tmp_path / "business.sqlite3")
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('auth_paused','1')")
    conn.commit()
    @contextmanager
    def operation():
        yield online(success)
    monkeypatch.setattr(auth_service, "session_operation", operation)
    def blocked(*args, **kwargs):
        raise HelperError("cookie_update_unknown", "synthetic unknown")
    monkeypatch.setattr(auth_service, "call_mtop", blocked)
    with pytest.raises(HelperError): auth_service.clear_pause(conn)
    assert conn.execute("SELECT value FROM meta WHERE key='auth_paused'").fetchone()[0] == "1"
    monkeypatch.setattr(auth_service, "call_mtop", lambda *args, **kwargs: {"ret":["SUCCESS"]})
    auth_service.clear_pause(conn)
    assert conn.execute("SELECT value FROM meta WHERE key='auth_paused'").fetchone() is None
    conn.close()

"""API route behavior against an isolated database without a live HTTP server."""

from __future__ import annotations

import asyncio
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException
from pydantic import ValidationError

from xianyu_radar import config as cfg
from xianyu_radar.entrypoints.api.app import SameOriginWriteMiddleware, create_app
from xianyu_radar.entrypoints.api.server import main as serve_main
from xianyu_radar.entrypoints.api.deps import get_db
from xianyu_radar.entrypoints.api.routes import auth, candidates, discover, events, pool, scan, status
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.seller_repository import add_seller_from_discovery
from xianyu_radar.models import SellerItem
from xianyu_radar.modules.scan.fetcher import get_seller_items_from_payload
from xianyu_radar.modules.scan.models import SellerCatalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cfg, "DEBUG_DIR", tmp_path / "debug")
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "radar.sqlite3")
    connection = init_db()
    try:
        yield connection
    finally:
        connection.close()


def test_app_has_one_data_environment() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/health" in paths
    assert "/api/discover" in paths
    assert "/api/discover/runs" in paths
    assert "/api/pool/{seller_id}" in paths
    assert "/api/scan/runs" in paths
    assert "/api/env" not in paths
    assert "/api/demo/offline-loop" not in paths
    assert "fixture" not in discover.DiscoverBody.model_fields
    assert "fixture" not in scan.ScanSellerBody.model_fields
    with pytest.raises(ValidationError):
        discover.DiscoverBody(keyword="Sony A7M4", fixture="tests/fixtures/search_results.json")
    with pytest.raises(ValidationError):
        scan.ScanSellerBody(fixture="tests/fixtures/shop_items.json")
    assert status.health()["ok"] is True


def test_manual_seller_add_is_idempotent_and_preserves_paused_state(conn) -> None:
    first = pool.add_seller(pool.AddSellerBody(reference="12345", nickname="示例"), conn)
    assert first == {"seller_id": "12345", "added": True, "status": "watching"}
    pool.patch_seller("12345", pool.StatusBody(status="paused"), conn)
    second = pool.add_seller(pool.AddSellerBody(
        reference="https://www.goofish.com/personal?userId=12345&foo=bar"
    ), conn)
    assert second == {"seller_id": "12345", "added": False, "status": "paused"}
    assert conn.execute("SELECT COUNT(*) FROM seller_pool_entries").fetchone()[0] == 1
    assert pool.get_seller_detail("12345", conn=conn)["seller"]["nickname"] == "示例"


def test_candidate_rule_endpoints_and_unknown_scan(conn) -> None:
    pool.add_seller(pool.AddSellerBody(reference="12345"), conn)
    assert pool.patch_candidate_rules("12345", pool.CandidateRulesBody(exclude_patterns=["FDE"]), conn)["updated"]
    assert pool.preview_candidate_rules("12345", conn=conn)["exclude_patterns"] == ["FDE"]
    assert pool.get_seller_detail("12345", conn=conn)["seller"]["candidate_exclude_patterns"] == ["FDE"]
    with pytest.raises(HTTPException) as error:
        pool.patch_candidate_rules("12345", pool.CandidateRulesBody(exclude_patterns=["!!"]), conn)
    assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        pool.preview_candidate_rules("missing", conn=conn)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        scan.get_candidate_decisions("missing", conn=conn)
    assert error.value.status_code == 404


def test_seller_metadata_normalizes_tags_and_survives_repeat_add(conn) -> None:
    pool.add_seller(pool.AddSellerBody(reference="12345"), conn)
    pool.patch_metadata("12345", pool.SellerMetadataBody(notes="  已验证的同品商家  ", tags=[" FDE ", "FDE", "重点", ""]), conn)
    pool.add_seller(pool.AddSellerBody(reference="12345"), conn)
    seller = pool.get_seller_detail("12345", conn=conn)["seller"]
    assert seller["notes"] == "已验证的同品商家"
    assert seller["tags"] == ["FDE", "重点"]
    assert pool.get_pool(conn=conn)["sellers"][0]["tags"] == ["FDE", "重点"]
    with pytest.raises(HTTPException) as error:
        pool.patch_metadata("missing", pool.SellerMetadataBody(notes="", tags=[]), conn)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        pool.patch_metadata("12345", pool.SellerMetadataBody(notes="", tags=["a" * 41]), conn)
    assert pool.get_seller_detail("12345", conn=conn)["seller"]["tags"] == ["FDE", "重点"]
    pool.patch_metadata("12345", pool.SellerMetadataBody(notes="", tags=[]), conn)
    assert pool.get_seller_detail("12345", conn=conn)["seller"]["tags"] == []


@pytest.mark.parametrize("reference", ["0", "unknown:123", "１２３", "-1",
    "https://evil.example/personal?userId=123", "https://www.goofish.com/item?id=123",
    "https://www.goofish.com/personal?userId=123&userId=456"])
def test_manual_seller_rejects_invalid_reference_without_writes(conn, reference) -> None:
    with pytest.raises(HTTPException) as error:
        pool.add_seller(pool.AddSellerBody(reference=reference), conn)
    assert error.value.status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 0


def test_web_rejects_cross_site_writes() -> None:
    called = []
    sent = []

    async def inner(scope, receive, send):
        called.append(scope)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = SameOriginWriteMiddleware(inner)
    scope = {
        "type": "http", "method": "POST", "scheme": "http", "path": "/api/auth/clear-pause",
        "headers": [(b"host", b"testserver"), (b"origin", b"https://example.invalid")],
    }
    asyncio.run(middleware(scope, receive, send))
    assert not called
    assert sent[0]["status"] == 403

    scope["headers"] = [(b"host", b"testserver"), (b"origin", b"http://testserver")]
    asyncio.run(middleware(scope, receive, send))
    assert len(called) == 1


def test_web_server_refuses_nonlocal_binding() -> None:
    with pytest.raises(SystemExit):
        serve_main(["--host", "0.0.0.0"])


def test_pool_detail_and_run_history_read_stored_data(conn) -> None:
    add_seller_from_discovery(
        conn, seller_id="SELLER_TEST", nickname="Example", source_keyword="camera", source_item_id="seed"
    )
    for item_id in ("item-1", "item-2"):
        conn.execute(
            "INSERT INTO items(item_id, seller_id, title, price, url, first_seen_at, last_seen_at) "
            "VALUES (?, 'SELLER_TEST', ?, '12', ?, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')",
            (item_id, item_id, f"https://www.goofish.com/item?id={item_id}"),
        )
    conn.execute(
        "INSERT INTO discovery_runs(id, keyword, started_at, status, item_count, seller_count) "
        "VALUES ('discover-1', 'camera', '2026-01-01T00:00:00Z', 'ok', 2, 1)"
    )
    conn.execute(
        "INSERT INTO scans(id, seller_id, started_at, status, item_count, event_count) "
        "VALUES ('scan-1', 'SELLER_TEST', '2026-01-02T00:00:00Z', 'ok', 2, 1)"
    )
    conn.commit()

    detail = pool.get_seller_detail("SELLER_TEST", limit=1, offset=1, conn=conn)
    assert detail["seller"]["nickname"] == "Example"
    assert detail["entries"][0]["source_item_id"] == "seed"
    assert detail["total_items"] == 2
    assert len(detail["items"]) == 1
    assert discover.get_discovery_runs(conn=conn)["runs"][0]["keyword"] == "camera"
    assert scan.get_scan_runs(seller="SELLER_TEST", conn=conn)["runs"][0]["event_count"] == 1
    assert scan.get_scan_runs(seller="OTHER", conn=conn)["total"] == 0
    with pytest.raises(HTTPException) as error:
        pool.get_seller_detail("MISSING", conn=conn)
    assert error.value.status_code == 404


def test_catalog_filters_and_failed_scan_keep_complete_reference(conn) -> None:
    pool.add_seller(pool.AddSellerBody(reference="12345"), conn)
    conn.executemany(
        "INSERT INTO items(item_id,seller_id,title,status,first_seen_at,last_seen_at) "
        "VALUES (?,'12345',?,?, 't','t')",
        [("1", "FDE v1", "active"), ("2", "FDE v2", "removed"), ("3", "100% 教程", "active")],
    )
    conn.execute("INSERT INTO scans(id,seller_id,started_at,status,item_count) VALUES ('ok','12345','t','ok',3)")
    conn.execute("INSERT INTO scans(id,seller_id,started_at,status,error_kind) VALUES ('bad','12345','t','failed','incomplete')")
    conn.commit()
    data = pool.get_seller_detail("12345", query="fde", item_status="active", limit=1, offset=0, conn=conn)
    assert data["total_items"] == 1
    assert data["items"][0]["item_id"] == "1"
    assert data["latest_complete_scan"]["id"] == "ok"
    assert data["latest_scan"]["id"] == "bad"
    assert pool.get_seller_detail("12345", query="%", conn=conn)["total_items"] == 1
    assert pool.get_seller_detail("12345", query="fde", limit=1, offset=1, conn=conn)["items"][0]["item_id"] == "2"


def test_events_and_candidates_have_stable_pages_and_totals(conn) -> None:
    add_seller_from_discovery(
        conn, seller_id="SELLER_TEST", nickname="Example", source_keyword="camera", source_item_id=None
    )
    for number in range(3):
        conn.execute(
            "INSERT INTO item_events(item_id, seller_id, event_type, old_value, new_value, "
            "detected_at, scan_id) VALUES (?, 'SELLER_TEST', 'PRICE_CHANGED', '10', '12', "
            "'2026-01-02T00:00:00Z', 'scan-1')",
            (f"item-{number}",),
        )
        conn.execute(
            "INSERT INTO candidates(normalized_title, sample_title, sample_price, sample_url, "
            "first_seen_at, last_seen_at, score) VALUES (?, ?, '12', 'https://www.goofish.com/', "
            "'2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', 1)",
            (f"candidate-{number}", f"Candidate {number}"),
        )
    conn.commit()

    conn.execute(
        "UPDATE candidates SET quality_flag='legacy_unverified' WHERE normalized_title='candidate-0'"
    )
    conn.commit()

    first_events = events.get_events(since="", limit=2, offset=0, conn=conn)
    next_events = events.get_events(since="", limit=2, offset=2, conn=conn)
    assert first_events["total"] == next_events["total"] == 3
    assert len(first_events["events"]) == 2
    assert len(next_events["events"]) == 1
    assert first_events["events"][0]["id"] != next_events["events"][0]["id"]
    first_candidates = candidates.get_candidates(since="", limit=2, offset=0, conn=conn)
    next_candidates = candidates.get_candidates(since="", limit=2, offset=2, conn=conn)
    assert first_candidates["total"] == next_candidates["total"] == 3
    assert len(first_candidates["candidates"]) == 2
    assert len(next_candidates["candidates"]) == 1
    assert first_candidates["candidates"][0]["candidate_id"] != next_candidates["candidates"][0]["candidate_id"]
    normal = candidates.get_candidates(since="", quality="normal", conn=conn)
    legacy = candidates.get_candidates(since="", quality="legacy_unverified", conn=conn)
    assert normal["total"] == 2
    assert legacy["total"] == 1
    assert legacy["candidates"][0]["quality_flag"] == "legacy_unverified"


def test_candidate_overview_keeps_status_filter_out_of_summary(conn) -> None:
    records = [
        ("old", "2026-01-01T00:00:00Z", "legacy_unverified", "new", 1),
        ("new", "2026-01-03T00:00:00Z", "normal", "new", 2),
        ("validated", "2026-01-04T00:00:00Z", "normal", "validated", 3),
        ("rejected", "2026-01-05T00:00:00Z", "normal", "rejected", 1),
    ]
    conn.executemany(
        "INSERT INTO candidates(normalized_title, first_seen_at, last_seen_at, "
        "quality_flag, status, seller_count) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (name, seen, seen, quality, status, sellers)
            for name, seen, quality, status, sellers in records
        ],
    )
    conn.commit()

    overview = candidates.get_candidates(
        since="2026-01-03T00:00:00Z", quality="normal", status="validated", conn=conn
    )
    assert overview["total"] == 1
    assert [row["normalized_title"] for row in overview["candidates"]] == ["validated"]
    assert overview["summary"] == {
        "total": 3,
        "multi_seller": 2,
        "by_status": {"new": 1, "rejected": 1, "validated": 1},
    }

    candidate_id = overview["candidates"][0]["candidate_id"]
    candidates.patch_candidate(
        candidate_id, candidates.CandidateStatusBody(status="testing"), conn
    )
    updated = candidates.get_candidates(
        since="2026-01-03T00:00:00Z", quality="normal", status="validated", conn=conn
    )
    assert updated["total"] == 0
    assert updated["summary"]["by_status"] == {"new": 1, "rejected": 1, "testing": 1}
    legacy = candidates.get_candidates(since="", quality="legacy_unverified", conn=conn)
    assert legacy["summary"]["total"] == 1


def test_api_database_connection_survives_worker_thread_switch(conn) -> None:
    dependency = get_db()
    api_conn = next(dependency)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            count = executor.submit(
                lambda: api_conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0]
            ).result()
        assert count == 0
    finally:
        with pytest.raises(StopIteration):
            next(dependency)


def test_auth_and_discover_use_the_same_data_store(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    saved = auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=samplelongtoken_1710000000000; a=1"}),
        conn,
    )
    assert saved["ok"] is True
    assert auth.auth_status(conn)["looks_like_placeholder"] is False

    response = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    response["data"]["resultList"][0]["data"]["item"]["main"]["clickParam"]["args"]["seller_id"] = "998877"
    monkeypatch.setattr(
        "xianyu_radar.modules.discovery.keyword_search.call_mtop",
        lambda *args, **kwargs: response,
    )

    found = discover.discover(
        discover.DiscoverBody(keyword="Sony A7M4", no_enrich=True),
        conn,
    )
    assert found["item_count"] == 1
    assert found["new_sellers"] == 1
    assert status.status(conn)["counts"]["items"] == 1
    assert status.status(conn)["counts"]["watching_sellers"] == 1


def test_invalid_cookie_cannot_overwrite_saved_session(conn, tmp_path: Path) -> None:
    auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=validtoken_1710000000000; a=1"}),
        conn,
    )
    path = tmp_path / "state/default.json"
    before = path.read_text(encoding="utf-8")
    with pytest.raises(HTTPException):
        auth.save_session(auth.SessionBody(payload={"cookie": "a=1"}), conn)
    assert path.read_text(encoding="utf-8") == before
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_detail_validation_failure_is_visible_and_does_not_create_sellers(
    conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=samplelongtoken_1710000000000; a=1"}),
        conn,
    )
    response = json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(
        "xianyu_radar.modules.discovery.keyword_search.call_mtop",
        lambda *args, **kwargs: response,
    )

    def blocked_detail(*args):
        raise MtopError("x5sec / USER_VALIDATE required", ret=["FAIL_SYS_USER_VALIDATE"])

    monkeypatch.setattr("xianyu_radar.modules.discovery.enrichment.fetch_detail", blocked_detail)
    with pytest.raises(HTTPException) as error:
        discover.discover(discover.DiscoverBody(keyword="Sony A7M4"), conn)

    assert error.value.status_code == 403
    assert conn.execute("SELECT status FROM discovery_runs").fetchone()["status"] == "verification_required"
    assert conn.execute("SELECT COUNT(*) FROM sellers").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def test_placeholder_cannot_be_scanned(conn) -> None:
    with pytest.raises(HTTPException) as error:
        scan.scan_one("unknown:123456", scan.ScanSellerBody(), conn)
    assert error.value.status_code == 400


def test_scan_candidates_and_events_share_the_same_data_store(
    conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth.save_session(
        auth.SessionBody(payload={"cookie": "_m_h5_tk=samplelongtoken_1710000000000; a=1"}),
        conn,
    )
    add_seller_from_discovery(
        conn, seller_id="SELLER_TEST", nickname="Example", source_keyword="Sony A7M4", source_item_id=None
    )
    conn.commit()
    assert pool.get_pool(conn=conn)["count"] == 1

    response = json.loads((FIXTURES / "shop_items.json").read_text(encoding="utf-8"))
    items = get_seller_items_from_payload(response)
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items",
        lambda *args, **kwargs: SellerCatalog(items, len(items), 1, "total_count", True),
    )

    first = scan.scan_one(
        "SELLER_TEST",
        scan.ScanSellerBody(keyword="Sony A7M4"),
        conn,
    )
    assert first["status"] == "ok"
    new_item = SellerItem(
        item_id="999000111",
        title="Photoshop 完整教程",
        price="12",
        url="https://www.goofish.com/item?id=999000111",
    )
    monkeypatch.setattr(
        "xianyu_radar.modules.scan.service.get_seller_items",
        lambda *args, **kwargs: SellerCatalog(items + [new_item], len(items) + 1, 1, "total_count", True),
    )
    second = scan.scan_one(
        "SELLER_TEST",
        scan.ScanSellerBody(keyword="Sony A7M4"),
        conn,
    )
    assert second["candidates"]["added"] >= 1
    listed = candidates.get_candidates(conn=conn)
    assert listed["count"] >= 1
    assert events.get_events(conn=conn)["count"] >= 1

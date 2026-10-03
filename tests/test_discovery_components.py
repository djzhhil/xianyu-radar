"""Focused coverage for discovery's internal components."""

import json
from contextlib import nullcontext

import pytest

from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.goofish.session import AuthError
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.modules.discovery.diagnostics import detail_diagnostic, error_kind_for
from xianyu_radar.modules.discovery.enrichment import enrich_pending

from xianyu_radar.modules.discovery.pagination import following_page


class Page(list):
    pass


@pytest.mark.parametrize("signal, expected", [
    (False, (0, None)), ("false", (0, None)), (0, (0, None)),
    (True, (2, None)), ("true", (2, None)), (3, (3, None)),
    ("4", (4, None)), (1, (1, "invalid_next_page")),
    ("invalid", (1, "invalid_next_page")),
])
def test_explicit_next_page(signal, expected):
    found = Page()
    found.next_page = signal
    assert following_page(found, 1, 30) == expected


@pytest.mark.parametrize("raw_count, expected", [(30, (2, None)), (29, (0, None))])
def test_next_page_falls_back_to_raw_count(raw_count, expected):
    found = Page()
    found.raw_count = raw_count
    assert following_page(found, 1, 30) == expected


def test_next_page_uses_has_next_when_next_page_missing():
    found = Page()
    found.has_next = True
    assert following_page(found, 2, 30) == (3, None)


@pytest.mark.parametrize("error, expected", [
    (AuthError("expired"), "auth"),
    (MtopError("x5sec", ret=["FAIL_SYS_USER_VALIDATE"]), "verification_required"),
    (MtopError("RGV587", ret=[]), "rate_limit"),
    (MtopError("timeout", ret=[]), "network"),
    (ValueError("invalid"), "parse_failed"),
])
def test_discovery_error_classification(error, expected):
    assert error_kind_for(error) == expected


def test_detail_diagnostic_keeps_field_names_not_values():
    detail = {"data": {"sellerDO": {"sellerId": "123", "nick": "private-name", "bad/key": "secret"}}}
    assert json.loads(detail_diagnostic(detail, "123")) == {
        "source": "sellerDO", "detail_fields": ["nick", "sellerId"],
    }
    assert json.loads(detail_diagnostic({"data": []}, None)) == {
        "source": "unresolved", "detail_fields": [],
    }


@pytest.mark.parametrize("retry_succeeds", [True, False])
def test_enrichment_retries_and_obeys_item_limit(tmp_path, monkeypatch, retry_succeeds):
    conn = init_db(tmp_path / "enrichment.sqlite3")
    conn.execute("INSERT INTO discovery_runs(id, keyword, started_at, status) VALUES ('run', 'test', 't', 'running')")
    conn.executemany(
        "INSERT INTO discovery_items(run_id, item_id, title, price, url, resolution) "
        "VALUES ('run', ?, '', '', '', 'pending')", [("1",), ("2",)],
    )
    conn.commit()
    calls = []

    def detail(_session, item_id, _client):
        calls.append(item_id)
        if len(calls) == 1 or not retry_succeeds:
            raise MtopError("timeout", ret=[])
        return {"data": {"sellerDO": {"sellerId": "123", "nick": "seller"}}}

    monkeypatch.setattr("xianyu_radar.modules.discovery.enrichment.fetch_detail", detail)
    monkeypatch.setattr("xianyu_radar.modules.discovery.enrichment.make_mtop_client", lambda: nullcontext(None))
    monkeypatch.setattr("xianyu_radar.modules.discovery.enrichment.time.sleep", lambda _: None)
    result = enrich_pending(conn, "run", session=Session("cookie", "token", "test"), max_enrich=1)
    assert result == (None, None)
    assert calls == ["1", "1"]
    rows = conn.execute("SELECT seller_id, resolution, error_kind FROM discovery_items ORDER BY item_id").fetchall()
    assert tuple(rows[0]) == (("123", "detail", None) if retry_succeeds else (None, "detail_error", "network"))
    assert rows[1]["resolution"] == "pending"
    conn.close()

"""Fixed Helper contract, cookie protocol, lifecycle and MTOP failure tests.

All credentials are synthetic. No Helper, platform or business database is
contacted; network requests are intercepted at separate HTTP transports.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs
from pathlib import Path

import httpx
import pytest

from xianyu_radar.infrastructure.goofish.cookie_jar import CookieJar, TOP_SITE, allowed_url
from xianyu_radar.infrastructure.goofish.errors import AuthError, HelperError
from xianyu_radar.infrastructure.goofish.mtop import MtopError, call_mtop, create_sign
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.helper.client import HelperClient, HelperConfig
from xianyu_radar.infrastructure.helper import session_provider as provider

CONFIG = HelperConfig("https://helper.example.test", "synthetic-user", "synthetic-password", "account-1")
MTOP = "https://h5api.m.goofish.com/h5/example/1.0/"
PAGE = "https://www.goofish.com/search"
NOW = datetime.now(timezone.utc)


def cookie(name="_m_h5_tk", value="old_123", **kwargs):
    return {"name": name, "value": value, "domain": ".goofish.com", "path": "/", "secure": True, **kwargs}


def snapshot(**kwargs):
    return {"account_id": "account-1", "credential_version": "v1:opaque", "snapshot_complete": True,
            "cookies": [cookie(), cookie("session", "synthetic-session", httpOnly=True)], **kwargs}


def updated(**kwargs):
    return {"account_id": "account-1", "credential_version": "v1:next", "changed": True,
            "runtime_sync_status": "synced", **kwargs}


def batch(headers=None):
    return {"response_url": MTOP, "received_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "set_cookies": headers or ["a=synthetic; Domain=.goofish.com; Path=/; Secure"]}


def helper(handler):
    def transport(req):
        assert req.url.host == "helper.example.test"
        if req.url.path == "/api/v1/session/login":
            assert json.loads(req.content) == {"username": CONFIG.username, "password": CONFIG.password}
            assert "synthetic-session" not in req.headers.get("cookie", "")
            return httpx.Response(200, headers={"set-cookie": "helper_auth=synthetic-admin; Path=/; Secure"}, json={"ok": True})
        assert req.headers["cookie"] == "helper_auth=synthetic-admin"
        return handler(req)
    return HelperClient(CONFIG, transport=httpx.MockTransport(transport))


def session(submit=None, cookies=None):
    return Session(source="Helper", jar=CookieJar(cookies or snapshot()["cookies"]),
                   credential_version="v1:opaque", account_id="account-1",
                   submit_updates=submit or (lambda batches: updated()))


def test_contract_paths_fields_and_version():
    seen = []
    def handler(req):
        seen.append(req)
        if req.method == "GET":
            assert req.url.path == "/api/v1/integrations/accounts/account-1/cookie-snapshot"
            return httpx.Response(200, json=snapshot())
        assert req.url.path == "/api/v1/integrations/accounts/account-1/cookie-updates"
        payload = json.loads(req.content)
        assert set(payload) == {"credential_version", "responses"}
        assert payload["credential_version"] == "v1:opaque"
        assert set(payload["responses"][0]) == {"response_url", "received_at", "set_cookies"}
        return httpx.Response(200, json=updated())
    client = helper(handler)
    try:
        jar, version = client.snapshot()
        assert jar.token(PAGE) == "old"
        assert client.updates(version, [batch()])["credential_version"] == "v1:next"
        assert len(seen) == 2
    finally:
        client.close()
    assert not client.http.cookies
    assert CONFIG.password not in repr(CONFIG)


@pytest.mark.parametrize("change", [
    {"snapshot_complete": False}, {"cookies": []}, {"cookies": "flat"},
    {"account_id": "different"}, {"credential_version": ""},
    {"cookies": [{"name": "a", "value": "fixture"}]},
    {"cookies": [cookie(httpOnly="false")]}, {"cookies": [cookie(expires=True)]},
    {"cookies": [cookie(value="fixture\r\nInjected: header")]},
])
def test_snapshot_rejects_incomplete_or_malformed(change):
    client = helper(lambda req: httpx.Response(200, json=snapshot(**change)))
    with pytest.raises(HelperError) as error:
        client.snapshot()
    assert error.value.kind == "helper_contract"
    client.close()


@pytest.mark.parametrize("status,kind", [(403,"helper_permission"),(404,"helper_account"),
                                          (409,"cookie_snapshot_unavailable"),(500,"helper_unavailable")])
def test_snapshot_errors_are_dependency_errors(status, kind):
    client = helper(lambda req: httpx.Response(status, json={"error": "synthetic-secret-must-not-escape"}))
    with pytest.raises(HelperError) as error:
        client.snapshot()
    assert error.value.kind == kind
    assert "synthetic-secret" not in str(error.value)
    client.close()


@pytest.mark.parametrize("eventually_ok", [False, True])
def test_401_reauth_once(eventually_ok):
    calls = []
    def transport(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/login"):
            return httpx.Response(200, headers={"set-cookie": "helper=fixture; Path=/; Secure"})
        return httpx.Response(200, json=snapshot()) if eventually_ok and calls.count(req.url.path) == 2 else httpx.Response(401)
    client = HelperClient(CONFIG, transport=httpx.MockTransport(transport))
    if eventually_ok:
        client.snapshot()
    else:
        with pytest.raises(HelperError) as error:
            client.snapshot()
        assert error.value.kind == "helper_auth"
    assert sum(p.endswith("/login") for p in calls) == 2
    assert sum(p.endswith("/cookie-snapshot") for p in calls) == 2
    client.close()


def test_bad_password_not_retried():
    calls = []
    client = HelperClient(CONFIG, transport=httpx.MockTransport(lambda req: (calls.append(req), httpx.Response(401))[1]))
    with pytest.raises(HelperError) as error:
        client.snapshot()
    assert error.value.kind == "helper_auth" and len(calls) == 1
    client.close()


@pytest.mark.parametrize("failure,kind", [(409,"credential_conflict"),(500,"cookie_update_unknown"),
    (503,"cookie_update_unknown"),(400,"cookie_update_rejected"),(413,"cookie_update_rejected"),
    (httpx.ReadTimeout("synthetic-secret"),"cookie_update_unknown"),
    (httpx.ConnectError("synthetic-secret"),"cookie_update_unknown")])
def test_updates_never_replay_ambiguous_or_conflicting_commit(failure, kind):
    count = 0
    def handler(req):
        nonlocal count
        count += 1
        if isinstance(failure, Exception):
            raise failure
        return httpx.Response(failure, json={"error": "synthetic-secret"})
    client = helper(handler)
    with pytest.raises(HelperError) as error:
        client.updates("v1:opaque", [batch()])
    assert error.value.kind == kind and count == 1
    assert "synthetic-secret" not in str(error.value)
    client.close()


@pytest.mark.parametrize("change", [{"runtime_sync_status": "invalid"}, {"credential_version": ""},
                                     {"changed": "true"}, {"account_id": "other"}])
def test_invalid_update_success_is_unknown(change):
    client = helper(lambda req: httpx.Response(200, json=updated(**change)))
    with pytest.raises(HelperError) as error:
        client.updates("v1:opaque", [batch()])
    assert error.value.kind == "cookie_update_unknown"
    client.close()


@pytest.mark.parametrize("case", ["batches", "count", "header", "body", "future", "old", "host"])
def test_update_limits_stop_without_network(case):
    client = helper(lambda req: pytest.fail("invalid update must not reach network"))
    batches = [batch()]
    if case == "batches": batches *= 33
    if case == "count": batches[0]["set_cookies"] *= 129
    if case == "header": batches[0]["set_cookies"] = ["a=" + "x" * 8192]
    if case == "body": batches[0]["set_cookies"] = ["a=" + "x" * 4096] * 128
    if case in {"future", "old"}:
        batches[0]["received_at"] = (datetime.now(timezone.utc) + timedelta(seconds=60 if case == "future" else -660)).isoformat()
    if case == "host": batches[0]["response_url"] = "https://external.test/"
    with pytest.raises(HelperError) as error:
        client.updates("v1:opaque", batches)
    assert error.value.kind == "cookie_update_limit"
    client.close()


def test_helper_connection_failure_does_not_leak_request():
    client = HelperClient(CONFIG, transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("synthetic-password"))))
    with pytest.raises(HelperError) as error:
        client.snapshot()
    assert error.value.kind == "helper_unavailable"
    assert CONFIG.password not in str(error.value)
    client.close()


def test_cookie_scope_order_and_document_signing():
    jar = CookieJar([
        cookie(value="hidden_1", httpOnly=True), cookie(value="host_2", domain="www.goofish.com"),
        cookie(value="long_3", path="/search"), cookie("expired", "x", expires=1),
        cookie("wrong_partition", "x", partitionKey="https://other.test"),
        cookie("partition", "x", partitionKey=TOP_SITE),
        cookie("boundary", "x", path="/searcher"), cookie("api", "x", domain="h5api.m.goofish.com"),
    ])
    assert jar.token(PAGE) == "long"
    assert jar.header(PAGE) == "_m_h5_tk=long_3; _m_h5_tk=hidden_1; _m_h5_tk=host_2; partition=x"
    assert jar.header(MTOP) == "_m_h5_tk=hidden_1; partition=x; api=x"
    assert jar.header("http://www.goofish.com/search") == ""
    assert jar.token("https://www.goofish.com/search/next") == "long"
    assert jar.token("https://www.goofish.com/searcher") == "host"


def test_cookie_replacement_delete_and_original_max_age():
    jar = CookieJar([cookie("a", "first"), cookie("b", "second"), cookie("a", "scoped", path="/h5")])
    jar.apply(MTOP, ["a=new; Domain=goofish.com; Path=/; Max-Age=3600; Expires=Wed, 01 Jan 2020 00:00:00 GMT; Secure"], NOW)
    assert jar.cookies[0]["expires"] == int(NOW.timestamp()) + 3600
    assert jar.header(MTOP).startswith("a=scoped; a=new; b=second")
    jar.apply(MTOP, ["a=; Domain=.goofish.com; Path=/; Max-Age=0", "a=recreated; Domain=.goofish.com; Path=/"], NOW)
    assert [c["name"] for c in jar.cookies] == ["b", "a", "a"]
    assert jar.cookies[1]["value"] == "scoped"


@pytest.mark.parametrize("header", ["bad", "a=x; Domain=other.test", "a=x; Domain=com", "a=x; SameSite=None",
    "a=x; Partitioned", "__Secure-a=x", "__Host-a=x; Secure; Domain=.goofish.com; Path=/",
    "__Host-a=x; Secure", "a=x\r\nHeader: y"])
def test_browser_rejected_headers_ignored(header):
    jar = CookieJar([cookie()])
    jar.apply(MTOP, [header], NOW)
    assert len(jar.cookies) == 1


def test_host_only_defaults_and_partition_identity():
    jar = CookieJar([cookie("a", "plain")])
    jar.apply(MTOP, ["host=fixture; Secure; HttpOnly", "a=partition; Domain=.goofish.com; Path=/; Secure; Partitioned; SameSite=None"], NOW)
    assert jar.cookies[1]["domain"] == "h5api.m.goofish.com"
    assert jar.cookies[1]["path"] == "/h5/example/1.0"
    assert jar.cookies[2]["partitionKey"] == TOP_SITE
    assert jar.header(MTOP).startswith("host=fixture;")
    assert "host=" not in jar.header(PAGE)
    assert "a=plain; a=partition" in jar.header(MTOP)


@pytest.mark.parametrize("url", ["http://www.goofish.com/", "https://evil.test/", "https://www.goofish.com:444/",
                                  "https://user@www.goofish.com/", "https://www.goofish.com:bad/"])
def test_unallowed_urls(url):
    assert not allowed_url(url)


def test_mtop_rotated_token_committed_before_single_retry():
    events = []
    s = session(lambda batches: (events.append(("commit", batches[0])), updated())[1])
    def handler(req):
        events.append(("request", req))
        assert "helper_auth" not in req.headers["cookie"]
        data_str = parse_qs(req.content.decode())["data"][0]
        params = dict(req.url.params)
        token = "old" if len(events) == 1 else "new"
        assert params["sign"] == create_sign(token, params["t"], data_str)
        if len(events) == 1:
            return httpx.Response(200, headers=[("set-cookie", "_m_h5_tk=new_2; Domain=.goofish.com; Path=/; Secure"),
                ("set-cookie", "_m_h5_tk_enc=enc; Domain=.goofish.com; Path=/; Secure; Expires=Wed, 01 Jan 2031 00:00:00 GMT")],
                json={"ret": ["FAIL_SYS_TOKEN_EXOIRED::令牌过期"], "data": {}})
        assert s.credential_version == "v1:next"
        assert "_m_h5_tk=new_2" in req.headers["cookie"]
        return httpx.Response(200, json={"ret": ["SUCCESS::ok"], "data": {}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert call_mtop(s, "taobao.idlemtopsearch.pc.search", {"keyword": "测试"}, client=client)["data"] == {}
    assert [e[0] for e in events] == ["request", "commit", "request"]
    b = events[1][1]
    assert len(b["set_cookies"]) == 2 and "Expires=Wed," in b["set_cookies"][1]
    assert "?" not in b["response_url"] and "sign" not in b["response_url"]


@pytest.mark.parametrize("ret,expected", [
    ("FAIL_SYS_SESSION_EXPIRED", "auth"), ("FAIL_SYS_SID_INVALID", "auth"), ("FAIL_SYS_NEED_LOGIN", "auth"),
    ("FAIL_SYS_USER_VALIDATE", "verification_required"), ("RGV587_ERROR", "rate_limit"),
    ("FAIL_SYS_TOKEN_EMPTY", "token"), ("FAIL_SYS_TOKEN_EXPIRED", "token"), ("FAIL_SYS_TOKEN_EXOIRED", "token"),
])
def test_error_headers_commit_before_classification_and_no_loop(ret, expected):
    requests, commits = [], []
    s = session(lambda batches: (commits.append(batches.copy()), updated())[1])
    def handler(req):
        requests.append(req)
        return httpx.Response(200, headers={"set-cookie": "diagnostic=fixture; Domain=.goofish.com; Path=/"}, json={"ret": [ret], "data": {}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises((MtopError, AuthError)) as error:
            call_mtop(s, "example", {}, client=client)
        assert getattr(error.value, "kind") == expected
        with pytest.raises(HelperError):
            call_mtop(s, "example", {}, client=client)
    assert len(requests) == len(commits) == 1
    assert not s.jar.cookies


def test_two_expired_responses_only_one_business_retry():
    calls = []
    s = session()
    def handler(req):
        calls.append(req)
        return httpx.Response(200, headers={"set-cookie": f"_m_h5_tk=new{len(calls)}_2; Domain=.goofish.com; Path=/"}, json={"ret": ["TOKEN_EXPIRED"]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(MtopError) as error:
        call_mtop(s, "taobao.idlemtopsearch.pc.search", {}, client=client)
    assert error.value.kind == "token" and len(calls) == 2


@pytest.mark.parametrize("status,body,kind", [(500,"not-json","parse_failed"),(200,"not-json","parse_failed"),
    (200,'{"ret":{},"data":{}}',"parse_failed"),(429,"not-json","rate_limit"),
    (500,'{"ret":["SUCCESS"]}',"http")])
def test_http_and_body_errors_still_submit(status, body, kind):
    commits = []
    s = session(lambda batches: (commits.append(batches.copy()), updated())[1])
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body, headers={"set-cookie":"a=fixture; Path=/"}))) as client:
        with pytest.raises(MtopError) as error:
            call_mtop(s, "example", {}, client=client)
    assert error.value.kind == kind and len(commits) == 1


def test_body_read_failure_still_commits_received_headers():
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            raise httpx.ReadError("synthetic-cookie-must-not-escape")
            yield b""
    commits = []
    s = session(lambda batches: (commits.append(batches.copy()), updated())[1])
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=Broken(), headers={"set-cookie":"a=fixture; Path=/"}))) as client:
        with pytest.raises(MtopError) as error:
            call_mtop(s, "example", {}, client=client)
    assert len(commits) == 1 and "synthetic-cookie" not in str(error.value)


def test_redirect_hop_scope_order_and_host_only_cookie():
    requests, commits = [], []
    s = session(lambda batches: (commits.extend(batches.copy()), updated())[1])
    def handler(req):
        requests.append(req)
        if len(requests) == 1:
            return httpx.Response(302, headers=[("location","https://passport.goofish.com/next"),
                                                ("set-cookie","host=fixture; Path=/; Secure")])
        if len(requests) == 2:
            assert "host=fixture" not in req.headers["cookie"]
            assert req.method == "GET"
            return httpx.Response(302, headers=[("location","https://h5api.m.goofish.com/end"),
                                                ("set-cookie","cross=fixture; Domain=.goofish.com; Path=/; Secure")])
        assert "host=fixture" in req.headers["cookie"] and "cross=fixture" in req.headers["cookie"]
        return httpx.Response(200, json={"ret":["SUCCESS"]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        call_mtop(s, "example", {}, client=client)
    assert [b["response_url"] for b in commits] == ["https://h5api.m.goofish.com/h5/mtop.example/1.0/", "https://passport.goofish.com/next"]


@pytest.mark.parametrize("location", ["https://external.test/", "http://www.goofish.com/", "?same=1"])
def test_invalid_redirects_submit_updates_and_never_send_external(location):
    requests, commits = [], []
    s = session(lambda batches: (commits.extend(batches.copy()), updated())[1])
    def handler(req):
        requests.append(req)
        return httpx.Response(302, headers={"location": location, "set-cookie": "a=fixture; Path=/"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(MtopError):
        call_mtop(s, "example", {}, client=client)
    assert commits and len(requests) <= 2
    assert all(r.url.host == "h5api.m.goofish.com" for r in requests)


@pytest.mark.parametrize("sync", ["failed", "not_needed", "not_running", "synced"])
def test_noop_or_sync_failure_adopts_version_without_resubmission(sync):
    commits = []
    s = session(lambda batches: (commits.append(batches.copy()), updated(changed=False, runtime_sync_status=sync))[1])
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ret":["SUCCESS"]}, headers={"set-cookie":"a=fixture; Path=/"}))) as client:
        call_mtop(s, "example", {}, client=client)
    assert len(commits) == 1 and s.credential_version == "v1:next"


def test_update_conflict_invalidates_session_before_retry():
    calls = []
    def submit(batches):
        raise HelperError("credential_conflict", "synthetic-conflict")
    s = session(submit)
    def handler(req):
        calls.append(req)
        return httpx.Response(200, headers={"set-cookie":"_m_h5_tk=new_2; Domain=.goofish.com; Path=/"}, json={"ret":["TOKEN_EXPIRED"]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HelperError): call_mtop(s, "example", {}, client=client)
        with pytest.raises(HelperError): call_mtop(s, "example", {}, client=client)
    assert len(calls) == 1 and not s.jar.cookies


def test_missing_token_never_calls_business_or_local_fallback():
    s = session(cookies=[cookie("session", "fixture", httpOnly=True)])
    with httpx.Client(transport=httpx.MockTransport(lambda req: pytest.fail("no unsigned business request"))) as client:
        with pytest.raises(MtopError) as error: call_mtop(s, "example", {}, client=client)
    assert error.value.kind == "token"
    with pytest.raises(HelperError): call_mtop(Session("flat", "fixture", "offline"), "example", {})


@pytest.fixture
def configured_provider(monkeypatch):
    for key, value in zip(("BASE_URL", "USERNAME", "PASSWORD", "ACCOUNT_ID"),
                          (CONFIG.base_url, CONFIG.username, CONFIG.password, CONFIG.account_id)):
        monkeypatch.setenv("RADAR_HELPER_" + key, value)
    clients = []
    def factory(config):
        client = helper(lambda req: httpx.Response(200, json=snapshot() if req.method == "GET" else updated(runtime_sync_status="failed")))
        clients.append(client)
        return client
    monkeypatch.setattr(provider, "HelperClient", factory)
    return clients


def test_operation_cleanup_and_status_secret_isolation(configured_provider):
    with provider.session_operation() as s:
        assert s.jar.token(PAGE) == "old"
        s.submit_updates([batch()])
        assert "old_123" not in repr(s)
    assert s.closed and not s.jar.cookies and not s.credential_version
    assert not configured_provider[0].http.cookies
    state = provider.provider_status()
    assert state["runtime_sync_status"] == "failed"
    assert state["source"] == "Helper" and state["last_fetch_at"] and state["last_submit_at"]
    serialized = json.dumps(state)
    for secret in (CONFIG.password, "old_123", "synthetic-admin", "v1:opaque"):
        assert secret not in serialized


def test_concurrent_operations_serialize_fetch_and_release_on_cancel(configured_provider):
    entered, release, second_started, second_entered = (threading.Event() for _ in range(4))
    def first():
        with provider.session_operation() as s:
            entered.set()
            assert release.wait(3)
            raise KeyboardInterrupt()
    def second():
        second_started.set()
        with provider.session_operation() as s:
            second_entered.set()
            return s.account_id
    with ThreadPoolExecutor(max_workers=2) as executor:
        f = executor.submit(first)
        assert entered.wait(3)
        g = executor.submit(second)
        assert second_started.wait(3)
        assert not second_entered.wait(0.05)
        assert len(configured_provider) == 1
        release.set()
        with pytest.raises(KeyboardInterrupt): f.result(timeout=3)
        assert g.result(timeout=3) == CONFIG.account_id
    assert len(configured_provider) == 2
    assert all(not c.http.cookies for c in configured_provider)


def test_loop_refetches_each_round_and_releases_before_sleep(configured_provider, monkeypatch, tmp_path):
    from xianyu_radar.modules.scan import runner
    from xianyu_radar.infrastructure.storage.db import init_db
    monkeypatch.setattr(runner, "run_pool_once", lambda conn, s, **kwargs: [{"status":"ok"}])
    released = []
    def sleep(seconds):
        # A separate operation between rounds proves no lock spans the loop.
        with provider.session_operation(): released.append(True)
    monkeypatch.setattr(runner.time, "sleep", sleep)
    conn = init_db(tmp_path / "business.sqlite3")
    runner.run_loop(conn, max_rounds=2, interval_sec=0, jitter_sec=0)
    conn.close()
    assert len(configured_provider) == 3 and released == [True]


def test_update_snapshot_unavailable_uses_helper_error_code():
    client = helper(lambda req: httpx.Response(409, json={"code":"cookie_snapshot_unavailable", "message":"synthetic-secret"}))
    with pytest.raises(HelperError) as error:
        client.updates("v1:opaque", [batch()])
    assert error.value.kind == "cookie_snapshot_unavailable"
    assert "synthetic-secret" not in str(error.value)
    client.close()


@pytest.mark.parametrize("url", ["http://remote.example.test", "https://user:password@helper.example.test", "https://helper.example.test/path", "https://[broken", "https://helper.example.test:bad"])
def test_invalid_helper_config_stops_before_auth(monkeypatch, url):
    for key, value in zip(("BASE_URL", "USERNAME", "PASSWORD", "ACCOUNT_ID"), (url, "synthetic", "synthetic-secret", "fixture")):
        monkeypatch.setenv("RADAR_HELPER_" + key, value)
    with pytest.raises(HelperError) as error: HelperConfig.from_env()
    assert error.value.kind == "helper_config"
    assert "synthetic-secret" not in str(error.value)


def test_full_snapshot_keeps_external_scope_but_never_sends_it():
    jar = CookieJar([cookie(), cookie("other", "synthetic", domain=".taobao.com")])
    assert len(jar.cookies) == 2 and "other=" not in jar.header(MTOP)


@pytest.mark.parametrize("case", json.loads((Path(__file__).parent / 'fixtures/helper_cookie_protocol.json').read_text())["cases"], ids=lambda c: c["name"])
def test_helper_protocol_vectors(case):
    jar = CookieJar(case["snapshot"])
    if "set_cookies" in case:
        jar.apply(case["response_url"], case["set_cookies"], NOW)
    assert jar.header(case["request_url"]) == case["expected_header"]


def test_post_401_reauth_does_not_change_version_or_updates():
    calls, payloads = [], []
    def transport(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/login"):
            return httpx.Response(200, headers={"set-cookie":"helper=fixture; Path=/; Secure"})
        payloads.append(json.loads(req.content))
        return httpx.Response(401) if len(payloads) == 1 else httpx.Response(200, json=updated())
    client = HelperClient(CONFIG, transport=httpx.MockTransport(transport))
    client.updates("v1:opaque", [batch()])
    assert len(payloads) == 2 and payloads[0] == payloads[1]
    assert sum(p.endswith("/login") for p in calls) == 2
    client.close()


def test_loop_stops_before_next_round_on_unknown_commit(configured_provider, monkeypatch, tmp_path):
    from xianyu_radar.modules.scan import runner
    from xianyu_radar.infrastructure.storage.db import init_db
    monkeypatch.setattr(runner, "run_pool_once", lambda conn, s, **kwargs: [{"status":"failed","error_kind":"cookie_update_unknown"}])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: pytest.fail("must not start another round"))
    conn = init_db(tmp_path / "business.sqlite3")
    assert runner.run_loop(conn, max_rounds=2) is False
    conn.close()
    assert len(configured_provider) == 1


def test_unknown_or_mutating_api_is_never_automatically_retried():
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, headers={"set-cookie":"_m_h5_tk=new_2; Domain=.goofish.com; Path=/"}, json={"ret":["TOKEN_EXPIRED"]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(MtopError):
        call_mtop(session(), "unknown.write", {}, client=client)
    assert len(requests) == 1


def test_oversized_header_stops_redirect_before_next_hop_or_commit():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(302, headers={"location":"https://passport.goofish.com/next", "set-cookie":"a=" + "x" * 8192})
    s = session(lambda batches: pytest.fail("oversized increment must not be committed"))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(HelperError) as error:
        call_mtop(s, "example", {}, client=client)
    assert error.value.kind == "cookie_update_limit" and len(calls) == 1 and not s.jar.cookies


@pytest.mark.parametrize("header", ['a="unterminated', 'a=bad"', 'a="bad"trailing'])
def test_invalid_cookie_quotes_are_not_absorbed(header):
    jar = CookieJar([cookie()])
    jar.apply(MTOP, [header], NOW)
    assert len(jar.cookies) == 1


def test_epoch_expires_deletes_cookie():
    jar = CookieJar([cookie("a", "fixture")])
    jar.apply(MTOP, ["a=; Domain=.goofish.com; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"], NOW)
    assert not jar.cookies

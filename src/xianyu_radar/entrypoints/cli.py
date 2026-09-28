"""CLI entry for xianyu-radar."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from xianyu_radar import __version__
from xianyu_radar import config as cfg
from xianyu_radar.infrastructure.goofish.session import AuthError, load_session
from xianyu_radar.modules.candidates.service import list_candidates
from xianyu_radar.config import ensure_data_dirs
from xianyu_radar.modules.discovery.keyword_search import search
from xianyu_radar.modules.discovery.service import discover_sellers
from xianyu_radar.infrastructure.storage.auth_state import clear_auth_paused, is_auth_paused
from xianyu_radar.modules.scan.runner import run_loop, run_pool_once
from xianyu_radar.modules.scan.fetcher import get_seller_items
from xianyu_radar.modules.scan.service import scan_seller
from xianyu_radar.infrastructure.storage.seller_repository import list_pool, set_seller_status
from xianyu_radar.infrastructure.storage.db import get_schema_version, init_db, table_names


def _conn():
    return init_db()


def cmd_init_db(_: argparse.Namespace) -> int:
    conn = _conn()
    version = get_schema_version(conn)
    tables = sorted(table_names(conn))
    conn.close()
    print(f"db={cfg.DB_PATH}")
    print(f"schema_version={version}")
    print(f"tables={', '.join(tables)}")
    return 0


def cmd_auth_check(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    try:
        session = load_session(args.state)
    except AuthError as e:
        print(f"AUTH_FAIL: {e}")
        return 1
    print(f"AUTH_OK source={session.source}")
    print(f"cookie_count={session.cookie_count}")
    print(f"token_prefix={session.token[:8]}...")
    # optional live ping
    if args.ping:
        from xianyu_radar.infrastructure.goofish.mtop import call_mtop

        try:
            # lightweight: empty-ish search page 1 with tiny rows — still a real call
            call_mtop(
                session,
                "taobao.idlemtopsearch.pc.search",
                {
                    "pageNumber": 1,
                    "keyword": "test",
                    "fromFilter": False,
                    "rowsPerPage": 1,
                    "sortValue": "",
                    "sortField": "",
                    "customDistance": "",
                    "gps": "",
                    "propValueStr": {},
                    "customGps": "",
                    "searchReqFromPage": "pcSearch",
                    "extraFilterValue": "{}",
                    "userPositionJson": "{}",
                },
                {"spm_cnt": "a21ybx.search.0.0"},
            )
            print("PING_OK")
        except Exception as e:
            print(f"PING_FAIL: {e}")
            return 2
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    try:
        session = load_session(args.state)
    except AuthError as e:
        print(f"AUTH_FAIL: {e}")
        return 1
    items = search(args.keyword, session)
    for it in items:
        print(
            f"{it.item_id}\t{it.price}\t{it.seller_id or '-'}\t{it.title[:60]}"
        )
    print(f"count={len(items)}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    conn = _conn()
    try:
        session = load_session(args.state)
    except AuthError as e:
        conn.close()
        print(f"AUTH_FAIL: {e}")
        return 1
    summary = discover_sellers(
        conn,
        args.keyword,
        session=session,
        enrich=not args.no_enrich,
    )
    conn.close()
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "items"},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_pool_list(args: argparse.Namespace) -> int:
    conn = _conn()
    rows = list_pool(conn, status=None if args.all else "watching")
    conn.close()
    for r in rows:
        print(
            f"{r['seller_id']}\t{r['status']}\t{r.get('nickname') or '-'}\t"
            f"{r.get('keywords') or '-'}\tfail={r['consecutive_failures']}"
        )
    print(f"count={len(rows)}")
    return 0


def cmd_pool_set(args: argparse.Namespace) -> int:
    conn = _conn()
    set_seller_status(conn, args.seller_id, args.status)
    conn.close()
    print(f"seller={args.seller_id} status={args.status}")
    return 0


def cmd_fetch_seller(args: argparse.Namespace) -> int:
    try:
        session = load_session(args.state)
    except AuthError as e:
        print(f"AUTH_FAIL: {e}")
        return 1
    catalog = get_seller_items(session, args.seller_id)
    items = catalog.items
    if not catalog.complete:
        print(f"INCOMPLETE: {catalog.finish_reason} pages={catalog.page_count} ", file=sys.stderr)
        return 1
    if args.out == "json":
        print(
            json.dumps(
                [it.__dict__ for it in items],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for it in items:
            print(f"{it.item_id}\t{it.price}\t{it.title[:60]}")
        print(f"count={len(items)}")
    return 0


def cmd_scan_seller(args: argparse.Namespace) -> int:
    conn = _conn()
    try:
        session = load_session(args.state)
    except AuthError as e:
        conn.close()
        print(f"AUTH_FAIL: {e}")
        return 1
    hints = [k.strip() for k in (args.keyword or "").split(",") if k.strip()] or None
    result = scan_seller(conn, session, args.seller_id, keyword_hints=hints)
    conn.close()
    events = result.get("events") or []
    print(f"scan_id={result.get('scan_id')} status={result.get('status')}")
    for e in events:
        flag = " baseline" if e.is_baseline else ""
        print(f"  {e.event_type}\t{e.item_id}\t{e.old_value or ''} -> {e.new_value or ''}{flag}")
    print(f"events={len(events)} items={result.get('item_count', 0)}")
    return 0 if result.get("status") == "ok" else 1


def cmd_scan_pool(args: argparse.Namespace) -> int:
    conn = _conn()
    try:
        session = load_session(args.state)
    except AuthError as e:
        print(f"AUTH_FAIL: {e}")
        return 1
    if args.clear_auth_pause:
        clear_auth_paused(conn)
    results = run_pool_once(
        conn,
        session,
        on_result=lambda r: print(
            f"seller_scan status={r.get('status')} events={len(r.get('events') or [])} "
            f"err={r.get('error_kind')}"
        ),
    )
    conn.close()
    return 0 if all(r.get("status") in ("ok", "skipped") for r in results) else 1


def cmd_candidates(args: argparse.Namespace) -> int:
    conn = _conn()
    since = None
    if args.since:
        # support 24h / 7d / ISO
        s = args.since.strip().lower()
        now = datetime.now(timezone.utc)
        if s.endswith("h") and s[:-1].isdigit():
            since = (now - timedelta(hours=int(s[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif s.endswith("d") and s[:-1].isdigit():
            since = (now - timedelta(days=int(s[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            since = args.since
    rows = list_candidates(
        conn, since_iso=since,
        quality_flag=None if args.quality == "all" else args.quality,
        limit=args.limit,
    )
    conn.close()
    for r in rows:
        sellers = ",".join(r.get("source_sellers") or [])
        print(
            f"{r['candidate_id']}\tquality={r['quality_flag']}\t"
            f"sellers={r['seller_count']}\tscore={r['score']:.1f}\t"
            f"{r['sample_title']}\t[{sellers}]"
        )
    print(f"count={len(rows)}")
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    conn = _conn()
    sql = "SELECT * FROM item_events WHERE 1=1"
    params: list = []
    if args.seller:
        sql += " AND seller_id=?"
        params.append(args.seller)
    if args.since:
        s = args.since.strip().lower()
        now = datetime.now(timezone.utc)
        if s.endswith("h") and s[:-1].isdigit():
            since = (now - timedelta(hours=int(s[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            since = args.since
        sql += " AND detected_at>=?"
        params.append(since)
    sql += " ORDER BY detected_at DESC LIMIT ?"
    params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    for r in rows:
        print(
            f"{r['detected_at']}\t{r['event_type']}\t{r['seller_id']}\t{r['item_id']}\t"
            f"baseline={r['is_baseline']}"
        )
    print(f"count={len(rows)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    conn = _conn()
    try:
        session = load_session(args.state)
    except AuthError as e:
        print(f"AUTH_FAIL: {e}")
        return 1
    print(
        f"scheduler start interval={args.interval}s jitter={args.jitter}s "
        f"auth_paused={is_auth_paused(conn)}"
    )
    try:
        run_loop(
            conn,
            session,
            interval_sec=args.interval,
            jitter_sec=args.jitter,
            max_rounds=args.max_rounds,
            on_result=lambda r: print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"status={r.get('status')} events={len(r.get('events') or [])}"
            ),
        )
    except KeyboardInterrupt:
        print("stopped")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radar",
        description="Xianyu merchant monitoring & candidate discovery",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="Initialize SQLite schema")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("auth", help="Auth commands")
    auth_sub = p.add_subparsers(dest="auth_cmd", required=True)
    p_check = auth_sub.add_parser("check", help="Validate session file")
    p_check.add_argument("--state", default=None, help="Path to session JSON")
    p_check.add_argument("--ping", action="store_true", help="Optional live MTOP ping")
    p_check.set_defaults(func=cmd_auth_check)

    p = sub.add_parser("search", help="Keyword search")
    p.add_argument("--keyword", "-k", required=True)
    p.add_argument("--state", default=None)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("discover", help="Search + build seller pool")
    p.add_argument("--keyword", "-k", required=True)
    p.add_argument("--state", default=None)
    p.add_argument("--no-enrich", action="store_true")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("pool", help="Seller pool")
    pool_sub = p.add_subparsers(dest="pool_cmd", required=True)
    p_list = pool_sub.add_parser("list")
    p_list.add_argument("--all", action="store_true")
    p_list.set_defaults(func=cmd_pool_list)
    p_set = pool_sub.add_parser("set-status")
    p_set.add_argument("seller_id")
    p_set.add_argument("status", choices=["watching", "paused", "dropped"])
    p_set.set_defaults(func=cmd_pool_set)

    p = sub.add_parser("fetch-seller", help="Fetch seller on-sale items")
    p.add_argument("seller_id")
    p.add_argument("--state", default=None)
    p.add_argument("--out", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_fetch_seller)

    p = sub.add_parser("scan-seller", help="Fetch + snapshot + diff one seller")
    p.add_argument("seller_id")
    p.add_argument("--state", default=None)
    p.add_argument("--keyword", default=None, help="Comma-separated keyword hints for candidates")
    p.set_defaults(func=cmd_scan_seller)

    p = sub.add_parser("scan-pool", help="Scan all watching sellers once")
    p.add_argument("--state", default=None)
    p.add_argument("--clear-auth-pause", action="store_true")
    p.set_defaults(func=cmd_scan_pool)

    p = sub.add_parser("candidates", help="List candidate products")
    p.add_argument("--since", default="24h", help="e.g. 24h, 7d, or ISO time")
    p.add_argument("--quality", choices=["all", "normal", "legacy_unverified"], default="all")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("events", help="List item events")
    p.add_argument("--seller", default=None)
    p.add_argument("--since", default="24h")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_events)

    p = sub.add_parser("run", help="Scheduler loop over seller pool")
    p.add_argument("--state", default=None)
    p.add_argument("--interval", type=float, default=90)
    p.add_argument("--jitter", type=float, default=30)
    p.add_argument("--max-rounds", type=int, default=None)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("serve", help="Start web UI + API (uvicorn)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    return parser


def cmd_serve(args: argparse.Namespace) -> int:
    from xianyu_radar.entrypoints.api.server import main as serve_main

    serve_main(
        ["--host", args.host, "--port", str(args.port)]
        + (["--reload"] if args.reload else [])
    )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()

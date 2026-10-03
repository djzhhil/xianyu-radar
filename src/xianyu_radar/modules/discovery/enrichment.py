"""Seller enrichment through item detail requests."""

from __future__ import annotations

import random
import sqlite3
import time

from xianyu_radar.infrastructure.goofish.mtop import call_mtop, make_mtop_client
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.goofish.errors import STOP_KINDS
from xianyu_radar.modules.discovery.diagnostics import detail_diagnostic, error_kind_for
from xianyu_radar.modules.discovery.item_parser import extract_seller_id, extract_seller_nick
from xianyu_radar.modules.discovery import repository


def fetch_detail(session: Session, item_id: str, client=None) -> dict:
    return call_mtop(
        session, "taobao.idle.pc.detail",
        {"id": str(item_id), "returnItemDO": True, "needSellerDO": True},
        {"spm_cnt": "a21ybx.item.0.0"}, client=client,
    )


def enrich_pending(
    conn: sqlite3.Connection, run_id: str, *, session: Session, max_enrich: int,
    error_kind: str | None = None, caught: Exception | None = None,
) -> tuple[str | None, Exception | None]:
    # A platform block stops further requests; identified sellers remain usable.
    if error_kind not in STOP_KINDS and not session.stop_kind:
        pending = repository.pending_items(conn, run_id, max_enrich)
        if pending:
            with make_mtop_client() as client:
                for index, row in enumerate(pending):
                    if index:
                        time.sleep(0.4 + random.uniform(0, 0.4))
                    item_id = row["item_id"]
                    for attempt in range(2):
                        try:
                            detail = fetch_detail(session, item_id, client)
                            seller_id = extract_seller_id(detail)
                            seller_nick = extract_seller_nick(detail)
                            repository.save_detail_result(
                                conn, run_id, item_id, seller_id=seller_id, seller_nick=seller_nick,
                                diagnostic=detail_diagnostic(detail, seller_id),
                            )
                            break
                        except Exception as exc:
                            kind = error_kind_for(exc)
                            if kind in STOP_KINDS or session.stop_kind:
                                error_kind, caught = kind, exc
                                repository.set_item_error(conn, run_id, item_id, "blocked", kind)
                                break
                            if attempt == 0:
                                time.sleep(1.0 + random.uniform(0, 0.5))
                            else:
                                repository.set_item_error(conn, run_id, item_id, "detail_error", kind)
                    if error_kind in STOP_KINDS or session.stop_kind:
                        break
    return error_kind, caught

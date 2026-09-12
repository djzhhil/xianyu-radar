# Progress log (Phase 4)

## Task 01 — 工程骨架与数据库 schema
- **Date:** 2026-09-12
- **Result:** PASS (`pytest` schema tests)
- **Notes:** package + schema v1 + `radar init-db`

## Task 02 — Auth / MTOP
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** `create_sign` known vector; session JSON formats; `radar auth check`

## Task 03 — 关键词搜索最小版
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** fixture parse + online `search()` via MTOP

## Task 04 — 解析 itemId
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** URL / fleamarket / card fields

## Task 05 — 解析 sellerId
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** detail `sellerDO.sellerId`; enrich in discover

## Task 06 — Seller Pool
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** dedupe sellers + multi keyword pool_entries

## Task 07 — get_seller_items
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** pagination merge mocked; fixture parse

## Task 08 — Snapshot
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** full snapshot each successful scan

## Task 09 — Diff engine
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** baseline / NEW / REMOVED(check_count>1) / PRICE / TITLE; empty → no REMOVED

## Task 10 — Candidate Pool
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** skip baseline & keyword-target; aggregate seller_count

## Task 11 — Scheduler
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** pool once + loop; auth_paused skip; jitter config

## Task 12 — E2E / docs
- **Date:** 2026-09-12
- **Result:** PASS
- **Notes:** `scripts/mvp_smoke.md`, README, session docs; offline smoke verified candidates

## Suite
- **pytest:** 27 passed (incl. API TestClient 联调)
- **MVP status:** COMPLETE (Phase 4)
- **Web UI:** FastAPI + `web/` · `radar serve --port 8765`
- **Live smoke:** `/api/demo/offline-loop` → candidates=1 · static assets OK

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
- **pytest:** 57 passed（2026-09-28，含扫描基线、分页完整性、候选迁移与模块边界回归测试）
- **MVP status:** COMPLETE (Phase 4)
- **Web UI:** FastAPI + `web/` · `radar serve --port 8765`
- **API 验证:** 发现 → 商家池 → 扫描 → 候选与事件，在临时数据库和模拟响应下通过；真实闲鱼请求尚需有效 Cookie

## Phase 5 — 数据可信度修复（2026-09-28）

- 首次成功店铺扫描按扫描记录判断基线；发现种子不会触发假上新。
- 分页抓取返回完整性诊断；不完整扫描不更新商品当前态、事件或候选。
- 商品数异常下降需要相同完整目录复扫确认；连续两次缺失才标记下架。
- 数据库从 v1 迁移到 v3；迁移前已用 SQLite backup API 备份。572 条旧候选标为 `legacy_unverified`，562 条 `new` 和 10 条 `rejected` 审核状态保留。
- 同卖家扫描加锁，池扫描增加卖家间隔；Cookie 原子保存为 `0600`；Web 限本机访问并拒绝跨站写入。
- 离线自动测试 57 项通过；未使用真实 Cookie 做在线采集验证。本沙箱无法连接本机 HTTP 端口，HTTP 联调未完成。

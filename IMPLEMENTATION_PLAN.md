# IMPLEMENTATION_PLAN.md

> Phase 3：把 `SYSTEM_DESIGN.md` 拆成可独立验收的小任务。  
> Phase 4 必须 **按 Task 顺序** 实现：测过 → 记进度 → 再下一个。禁止一次性生成整系统。

进度文件：本目录 `PROGRESS.md`（Phase 4 开始时创建并维护）。

---

## 总约定

| 项 | 约定 |
|----|------|
| 根目录 | `/root/projects/xianyu-radar/` |
| 包名 | `src/xianyu_radar/` |
| 研究目录 | `_research/` **只读** |
| 数据库 | `data/radar.sqlite3` |
| 登录态 | `data/state/` |
| 测试 | `pytest`；无网络单测优先用 fixtures |
| 完成定义 | 该 Task「验收标准」全部满足，并更新 `PROGRESS.md` |

---

## Task 01 — 工程骨架与数据库 schema

**目标：** 可安装的 Python 包 + SQLite schema 迁移可跑通。

**输入：** `SYSTEM_DESIGN.md` §5  
**输出：**

- `pyproject.toml` 或 `requirements.txt`
- `src/xianyu_radar/storage/schema.sql` + `db.py`（init/migrate）
- `src/xianyu_radar/config.py`
- `.gitignore`（`data/`、`__pycache__`、`.venv`）
- 空 `cli.py` 入口可 `python -m xianyu_radar.cli --help`

**涉及文件：** 上列新建文件  
**验收标准：**

1. `db.init_db()` 后存在 `sellers/items/item_snapshots/item_events/candidates/...` 表；
2. 重复执行 migrate 不报错；
3. 测试：`test_schema.py` 检查关键表存在。

**风险：** 过度建表；控制在设计文档第一版实体内。

---

## Task 02 — Auth / MTOP 最小客户端

**目标：** 从 state 文件加载 Cookie，完成签名与一次可注入的 `call_mtop`。

**输入：** zpl11 `xianyu_api.mjs` 签名逻辑；用户提供的 cookie 文件格式（可先支持「纯 Netscape/JSON cookies + 从中解析 `_m_h5_tk`」）  
**输出：**

- `auth/session.py`：`load_session(path) -> Session`
- `auth/mtop.py`：`call_mtop(session, api_name, data, extra=None)`
- CLI：`radar auth check`（校验 token 是否存在；可选打一个轻量 API）

**涉及文件：** `auth/*`, `cli.py`, `tests/test_mtop_sign.py`  
**验收标准：**

1. 单测：固定 token/t/data → sign 与已知 md5 一致；
2. 无 cookie 时 `auth check` 清晰失败，不崩溃；
3. **不**在无用户授权时对真实环境打高频请求。

**风险：** cookie 格式多样；先文档化一种 JSON 格式。

---

## Task 03 — 关键词搜索最小版

**目标：** `search(keyword) -> list[SeedItem]` 可独立运行。

**输入：** 关键词字符串  
**输出：**

- `discovery/keyword_search.py`
- `discovery/item_parser.py`（列表字段映射）
- fixtures：从 Asher `tests/fixtures/search_results.json` **脱敏拷贝** 一份到我们 `tests/fixtures/`
- CLI：`radar search --keyword K --dry-parse-fixture`（离线）与 `radar search --keyword K`（在线，需 auth）

**涉及文件：** `discovery/*`, fixtures, cli  
**验收标准：**

1. 离线解析 fixture 能得到 `item_id/title/price/url`（seller 可空）；
2. 在线路径封装单一函数，失败抛结构化错误；
3. 单测不依赖网络。

**风险：** 直签搜索不稳定 → 本 Task 接口固定，实现可标 `TODO: playwright adapter`，但必须先有一种可测路径（至少 fixture + 解析）。

---

## Task 04 — 解析 itemId（强化）

**目标：** 所有入口对 item 身份归一。

**输入：** 原始链接 / card / 详情 JSON  
**输出：** `item_parser.extract_item_id(...)` 统一函数  
**涉及文件：** `item_parser.py`, `tests/test_item_id.py`  
**验收标准：**

1. 能从 `https://www.goofish.com/item?id=123&xxx` 得到 `123`；
2. 能从 fixture cardData 得到稳定 id；
3. 缺失 id 的记录被丢弃或标记 invalid，不进入池。

**风险：** 多种 URL 形态；用表格用例覆盖。

---

## Task 05 — 解析 sellerId

**目标：** 从详情（或列表若存在）得到 `seller_id`。

**输入：** detail JSON fixture（可从研究材料脱敏）  
**输出：**

- `discovery/seller_discovery.py` 中 `extract_seller_id(detail) -> str`
- 可选 `fetch_detail(item_id)` 薄封装

**涉及文件：** discovery, fixtures, tests  
**验收标准：**

1. 从 `data.sellerDO.sellerId` 解析成功；
2. CLI：`radar enrich --item-id` 或 search 流水线中能打印 seller_id（在线可选）。

**风险：** detail 触发 x5sec；在线失败要可重试/跳过单条，不中断整批。

---

## Task 06 — 建立 Seller Pool

**目标：** 发现结果去重写入 `sellers` + `seller_pool_entries`。

**输入：** `discover_sellers(keyword)` 或手工 `pool add`  
**输出：**

- `sellers/pool.py`
- CLI：`radar discover --keyword K`（串联 search→enrich→pool）、`radar pool list`

**涉及文件：** sellers/pool, storage repos, cli  
**验收标准：**

1. 同一 seller 两次发现不重复建 sellers 行；
2. 第二次不同关键词增加 pool_entries；
3. `pool list` 显示 seller_id/nickname/status/来源关键词。

**风险：** 无 seller_id 的商品跳过并计数报告。

---

## Task 07 — `get_seller_items(seller_id)`

**目标：** 分页拉取卖家在售，独立可测。

**输入：** seller_id  
**输出：**

- `sellers/fetcher.py`
- 规范化 `SellerItem{item_id,title,price,url,raw_status}`
- CLI：`radar fetch-seller SELLER_ID --out json`
- fixture：基于 zpl11 `output.json` 脱敏片段做解析单测

**涉及文件：** fetcher, mtop, tests  
**验收标准：**

1. 解析 cardList 去重 item_id；
2. 分页逻辑用 mock HTTP 测「多页合并」；
3. 在线手动烟测（有 cookie 时）拉回非空或显式空。

**风险：** totalCount 与 nextPage 字段差异；兼容 zpl11 两种翻页信号。

---

## Task 08 — Snapshot 写入

**目标：** 一次成功 fetch 后写入/更新 items，并追加 snapshots。

**输入：** `list[SellerItem]` + seller_id + scan_id  
**输出：**

- `items/repository.py` upsert
- `items/history.py` append snapshots
- 更新 `sellers.last_scan_at`、`items.check_count`

**涉及文件：** items/*, storage  
**验收标准：**

1. 两次相同数据 → items 行更新 last_seen，snapshots 按策略追加（可「每次扫描都写」或「变化才写」；**选定并文档化**：建议 MVP **每次成功扫描写全量 snapshot** 便于审计，后期可降采样）；
2. 单测用临时 sqlite。

**风险：** 快照膨胀；后续加保留策略，本 Task 可先全量。

---

## Task 09 — Diff 引擎

**目标：** `current vs previous` → 标准事件。

**输入：** 上次 active items（DB）+ 本次 fetch 列表  
**输出：**

- `items/diff.py` → `list[ItemEvent]`
- 写入 `item_events`
- CLI：`radar scan-seller S` 打印事件摘要

**涉及文件：** diff, monitor, tests/test_diff.py  
**验收标准（表驱动单测）：**

| 场景 | 期望 |
|------|------|
| 卖家无历史 | 全部 NEW + `is_baseline=1`，不进候选 |
| 新增 id | `NEW_ITEM` |
| 缺少 id 且 check_count>1 | `REMOVED_ITEM` |
| 价变 | `PRICE_CHANGED` |
| 题变 | `TITLE_CHANGED` |
| 本次空列表 | **无 REMOVED**，scan failed |

**风险：** 字符串价格与空白标题；规范化后再比。

---

## Task 10 — Candidate Pool

**目标：** 非 baseline 的 NEW_ITEM → 候选；CLI 可查近 24h。

**输入：** events + watch keyword 规则  
**输出：**

- `candidates/detector.py` / `score.py` / `repository.py`
- CLI：`radar candidates --since 24h`

**涉及文件：** candidates/*, tests/test_candidate_detector.py  
**验收标准：**

1. 标题包含关键词 → 不入选；
2. 其他 NEW → 入选；同归一化标题聚合 seller_count；
3. `candidates` 输出含标题、来源卖家数、最近时间。

**风险：** 归一化过粗/过细；MVP 用 lower+去空白+全角半角简单规则。

---

## Task 11 — Scheduler 最小循环

**目标：** `radar run` 按池轮转扫描，带抖动与退避。

**输入：** 配置 interval、pool 中 watching 卖家  
**输出：**

- `scheduler/runner.py`
- 尊重 `auth_paused`、卖家 `paused`
- 日志：每轮 scan_id、事件计数

**涉及文件：** scheduler, config, cli  
**验收标准：**

1. 单测：mock monitor，验证顺序与「失败退避」被调用；
2. 手动短 interval 跑 2 轮不崩溃；
3. Ctrl+C 优雅退出并写完当前库事务。

**风险：** 别默认高频；配置默认偏慢（如 60s+jitter）。

---

## Task 12 — 端到端 MVP 验收脚本

**目标：** 对照用户第十一节做一次闭环证明。

**输入：** 真实 cookie + 测试关键词（用户提供）  
**输出：**

- `scripts/mvp_smoke.md` 或 `scripts/mvp_smoke.sh` 步骤说明
- `PROGRESS.md` 标记 MVP done
- README：如何 discover / scan / candidates

**验收标准：**

1. 文档步骤可复现；
2. DB 中能查出 pool、snapshots、candidates；
3. 明确列出已知限制（搜索适配器、x5sec 等）。

**风险：** 环境无 cookie 时改为「夹具模拟 E2E」+ 在线步骤标可选。

---

## Task 依赖图

```text
01 schema
 └─ 02 auth/mtop
      ├─ 03 search (+ 04 itemId)
      │    └─ 05 sellerId
      │         └─ 06 seller pool
      └─ 07 get_seller_items
           └─ 08 snapshot
                └─ 09 diff
                     └─ 10 candidates
                          └─ 11 scheduler
                               └─ 12 e2e / docs
```

04 可与 03 合并实现，但验收仍分开勾选。

---

## Phase 4 执行纪律

每完成一个 Task：

1. 跑该 Task 相关测试；
2. 抽查 sqlite（`sqlite3 data/radar.sqlite3`）；
3. 确认未破坏已完成 Task；
4. 更新 `PROGRESS.md`（日期、Task、结果、已知问题）；
5. 再开始下一 Task。

若某 Task 受阻（如搜索直签失败）：

- 保持函数接口；
- 实现 fallback 适配器或夹具路径；
- 在 PROGRESS 记录阻塞原因；
- **不**借机大重构无关模块。

---

## 明确不在 Phase 4 MVP 的 Task（冻结）

- Web UI
- AI 评分
- 自动上架/发货
- 五维统计
- 多账号轮换完整实现
- 修改 `_research/` 上游项目

---

## Phase 3 完成标准

| 项 | 状态 |
|----|------|
| Task 01–12 均有目标/输入/输出/文件/验收/风险 | ✅ |
| 依赖关系清晰 | ✅ |
| 与 SYSTEM_DESIGN / 业务链对齐 | ✅ |
| 未开始大规模业务编码 | ✅（进入 Phase 4 才编码） |

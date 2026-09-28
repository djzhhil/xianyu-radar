# 数据可信度修复计划

状态：R1–R4 已实施；R5 的扫描锁、请求间隔、Cookie 保存保护和本机 API 入口保护已实施。远程 Web 访问仍未开放，启动器会拒绝非本机监听地址。

## 依据与目标

2026-09-28 本地数据库显示：11 个商家、33 次成功扫描、590 条 `NEW_ITEM` 事件、572 条候选；590 条 `NEW_ITEM` 的 `is_baseline` 均为 0。按卖家最早的扫描记录统计，其中 535 条出自首次记录的扫描。另有一家店铺的三次商品数为 70→8→8。该记录只能说明存在数量异常，不能直接判断真实下架或抓取不完整。

修复目标：首次完整扫描只建档；只有完整且可信的扫描能产生变化事件和候选；历史候选可识别、可复核，人工审核状态保留。

## 调用边界（每项修改的硬约束）

每次实施及提交只沿一条现有执行链路改动：`web/CLI → 对应 API 路由或 CLI 命令 → 对应 modules/<业务>/service.py → 该业务目录内部函数 → infrastructure/ 与 SQLite`。同一业务目录内可以调用自己的函数；业务模块之间不得互相导入或调用，也不通过 API 内部互调。公共能力放在 `infrastructure/`，入口负责分发，模块之间只通过已经约定的 SQLite 数据衔接。一个任务需要两个入口链路时拆成两次提交，各自验收。

本次涉及的执行链路分别是：

| 任务 | 允许触及的运行链路 |
| --- | --- |
| R1、R3 扫描修复 | `routes/scan.py` 或 `cli.py` → `scan/runner.py` / `scan/service.py` → `scan/` 内部函数 → `infrastructure/goofish`、`infrastructure/storage`。`scan/candidate_detector.py` 保持扫描模块内部的候选写入职责。 |
| R2、R4 的迁移 | `app.py` / `api/deps.py` / CLI 初始化 → `infrastructure/storage/db.py` → SQL 迁移。迁移只处理表结构与旧数据，不调用业务模块。 |
| R4 候选展示 | `web/app.js` → `routes/candidates.py` → `candidates/service.py` → `candidates/repository.py` → SQLite；不回调扫描模块。 |
| R5 运行保护 | 扫描调度、登录态保存、API 入口各自单独实施，各自验收。 |

每个任务完成后运行 `tests/test_module_boundaries.py`；增强该测试，检查 `infrastructure/` 不导入 `modules/`，并维持各业务路由只进入自己的模块。测试中的跨模块场景通过数据库先准备数据、再从对应入口执行，不给生产代码增加跨模块调用。

## R1 — 首次扫描基线（P0，先实施）

### 根因

发现链路通过 `seller_repository.py::upsert_seed_item()` 在首次店铺扫描前已写入 `items`。`scan/diff.py` 用 `len(previous) == 0` 判断基线，种子商品使首次店铺扫描被误判为后续扫描。修复只发生在扫描链路；发现模块只是前置数据来源。

### 修改文件与做法

| 文件 | 修改思路 |
| --- | --- |
| `src/xianyu_radar/modules/scan/service.py`、`src/xianyu_radar/modules/scan/item_repository.py` | `apply_scan_result()` 写入本轮 `running` 记录前，查询该卖家是否存在 `status='ok'` 的历史扫描；据此确定 `is_baseline`，并显式传给差分函数。首次扫描的整份店铺目录作为基线写入快照，候选数应为 0。若发现阶段的种子商品未出现在首次完整店铺目录，将其状态设为 `unknown`，不生成下架事件。 |
| `src/xianyu_radar/modules/scan/diff.py` | 将 `baseline` 改为显式参数。基线时为本次目录里的每件商品生成 `is_baseline=True` 的 `NEW_ITEM` 建档事件；不比较种子商品带来的标题、价格差异，也不产生 `REMOVED_ITEM`。后续扫描才做正常差分。 |
| `tests/test_candidate_detector.py`、`tests/test_diff.py`、`tests/test_api.py` | 新增“先发现并写入种子 → 首次扫描多件商品 → 0 候选、全部新建事件均为基线 → 第二次确有新商品才产生候选”的回归用例。覆盖首次扫描店铺目录缺少种子商品的情况。 |

验收：首次扫描不会产生非基线事件或候选；第二次扫描新增非目标商品恰好产生相应事件和候选；原有测试继续通过。

## R2 — 扫描数据结构迁移（P0，扫描链路的公共存储）

执行链路：应用或 CLI 初始化 → `infrastructure/storage/db.py` → SQL。此次迁移只增加扫描所需字段，先在临时 v1 数据库和正式库副本上验证。

| 文件 | 修改思路 |
| --- | --- |
| `src/xianyu_radar/config.py`、`src/xianyu_radar/infrastructure/storage/db.py` | `SCHEMA_VERSION` 升到 2；按版本顺序执行迁移，并确保重复启动不重复修改。当前 `CREATE TABLE IF NOT EXISTS` 无法给旧表增加列。 |
| `src/xianyu_radar/infrastructure/storage/migrations/0002_scan_quality.sql`（新增）、`pyproject.toml` | 为 `scans` 增加期望商品数、页数、结束原因字段；为 `items` 增加连续缺失计数。保留 `schema.sql` 作为 v1 建库基线，新库也按 v1→v2 升级；把迁移 SQL 加入打包数据。 |
| `tests/test_schema.py` | 测 v1→v2 升级、新库初始化、重复升级和原数据保留。 |

## R3 — 分页完整性与数量异常（P0，接着实施）

### 根因

`scan/fetcher.py` 当前在空页、重复页、页数上限等情况下可能直接返回已收集的部分商品。`scan/service.py` 只阻止空列表，对非空但不完整的目录仍执行差分。`diff.py` 的 `check_count > 1` 规则又可能让首次见过、随后消失的商品长期停留在 `active`。

### 修改文件与做法

| 文件 | 修改思路 |
| --- | --- |
| `src/xianyu_radar/modules/scan/models.py`（新增） | 增加扫描模块专用的 `SellerCatalog`，包含 `items`、`expected_count`、`page_count`、`finish_reason`、`complete`；不扩大公共 `models.py` 的职责。 |
| `src/xianyu_radar/modules/scan/fetcher.py` | `get_seller_items()` 返回 `SellerCatalog`。核对每页 `totalCount` 一致、下一页不回跳、商品 ID 不重复导致提前停滞；到达 `max_pages`、预期总数未取满、非空原始卡片无法解析时标记不完整。只有达到明确结束条件且数量吻合时才设 `complete=True`。 |
| `src/xianyu_radar/modules/scan/service.py` | 不完整目录记为 `failed/incomplete`，记录已抓数与诊断信息，跳过 `apply_scan_result()`，因此不更新 `items`、不写变化事件或候选。完整目录较上次成功扫描大幅下降时，先记为 `suspect/count_drop` 并保存本次观测，不提交差分；初始告警规则可设为上次至少 20 件且下降超过 50%，作为可配置阈值。下一次完整扫描若商品 ID 集合与可疑观测一致，则确认变化并提交；若恢复原数量，则丢弃该次可疑观测；其余情况继续标记可疑。 |
| `src/xianyu_radar/modules/scan/diff.py`、`src/xianyu_radar/modules/scan/item_repository.py` | 将下架判断改成“连续两次完整目录缺失”，不再依赖商品曾被看到的 `check_count`。普通完整扫描首次缺失时把 `missing_count` 加 1；再次缺失达到 2 时只产生一次 `REMOVED_ITEM`。对于两次商品 ID 集合一致的 `suspect` 观测，确认时按两次缺失处理。重新出现时清零。 |
| `src/xianyu_radar/modules/scan/history.py` | 保存和查询抓取页数、平台总数、结束原因；`suspect` 扫描的商品 ID 观测可写入现有 `item_snapshots`，但不能当作已确认的商品当前态。 |
| `src/xianyu_radar/entrypoints/cli.py`、`src/xianyu_radar/entrypoints/api/routes/scan.py`、`web/app.js` | 适配 `SellerCatalog` 返回值，展示 `incomplete`、`count_drop` 与相关数量，让用户知道本轮为何没有事件。 |
| `tests/test_fetcher.py`、`tests/test_diff.py`、`tests/test_api.py` | 用模拟分页覆盖正常多页、总数不符、空的中间页、重复页、页数上限；用 70→8→8 覆盖先标可疑、复扫确认，再产生一次下架；验证不完整扫描不会改变业务表。 |

验收：不完整目录的事件数和候选数为 0；70→8 的首轮不产生下架，确认后只产生一次；已移除商品再次出现时按新出现处理。

## R4 — 历史候选标记与展示（P0，扫描修复后实施）

分两次修改：先沿公共存储初始化链路做 v3 迁移，再沿候选读取链路增加展示和筛选。两步均不调用扫描模块。

| 文件 | 修改思路 |
| --- | --- |
| `src/xianyu_radar/config.py`、`src/xianyu_radar/infrastructure/storage/db.py`、`src/xianyu_radar/infrastructure/storage/migrations/0003_candidate_quality.sql`（新增）、`pyproject.toml` | `SCHEMA_VERSION` 升到 3；给 `candidates` 增加 `quality_flag`，默认 `normal`。迁移时把升级前已有候选标为 `legacy_unverified`，原 `status` 保持不变。此步属于公共存储初始化链路。 |
| `src/xianyu_radar/modules/candidates/service.py`、`src/xianyu_radar/modules/candidates/repository.py`、`src/xianyu_radar/entrypoints/api/routes/candidates.py`、`web/app.js`、`web/index.html` | 候选页显示质量标记，并可筛选正常候选与旧数据。此步只沿候选读取链路修改；扫描模块依靠数据库默认值写入新候选。 |
| `tests/test_schema.py`、`tests/test_api.py` | 分别测 v2→v3 升级与重复升级、旧候选状态保留、候选 API 筛选结果与分页总数。 |

实施前使用 SQLite backup API 备份 `data/radar.sqlite3`，并记录备份文件位置。历史候选与事件缺少完整的逐条来源关系，因此旧数据统一标为“待核实”，不按时间批量推断哪些一定是假上新。对 70→8 的商家先复核后处理历史 `active` 商品。

## R5 — 运行保护（P1，在可信数据修复后）

| 文件 | 修改思路 |
| --- | --- |
| 扫描调度链路：`src/xianyu_radar/modules/scan/runner.py` | 同一卖家避免并发扫描；按单卖家控制请求间隔与退避，单独测试和交付。 |
| 登录态链路：`src/xianyu_radar/modules/auth/service.py` | 保存 Cookie 时用临时文件、`0600` 权限和原子替换；保存前验证 JSON 和 `_m_h5_tk`，单独测试和交付。 |
| API 入口链路：`src/xianyu_radar/entrypoints/api/app.py` | 对非本机部署增加入口层身份验证、限制 CORS 来源；不在各业务模块内添加认证调用，单独测试和交付。 |
| 文档：`PROGRESS.md`、`README.md`、`scripts/mvp_smoke.md` | 随对应任务记录结果、迁移步骤、历史数据标记含义和人工验收流程。 |

## 推荐实施顺序

1. 在临时数据库复现 R1，只修改扫描链路并验收。
2. 完成 R2 的 v2 存储迁移，再完成 R3 的扫描完整性保护；两个改动分别验收。
3. 完成 R4 的 v3 存储迁移，再完成候选展示链路；备份正式数据库，在副本上核对记录数量与人工状态后升级。
4. 跑完整测试、离线端到端流程和一次低频在线人工烟测；R5 的三个运行保护任务分别交付。

实施前的数据库备份位于 `data/backups/`。迁移保留原候选审核状态；在线烟测只在有效登录态下人工触发。

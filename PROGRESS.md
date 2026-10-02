# Progress log (Phase 4)

## T2.1 — 候选商品来源（2026-10-02）

- 分支：`codex/t2-candidate-sources`。
- v7 新增独立来源表；扫描上新保存商品、商家、标题、价格、图片、时间和扫描依据。共享写入置于基础存储组件，模块之间不互调内部函数。
- 新增候选来源分页 API 和来源类型汇总；重复来源去重，旧候选审核与质量不变，不补造历史来源。
- 验证：82 项测试通过，涵盖跨商家来源、重复计数、分页、旧候选保留及模块边界；迁移前已备份本地数据库。

## T2 前端准备 — 工作台布局重构（2026-10-02）

- 分支：`codex/t2-workbench-layout`，仅修改 Web 展示与交互、验收脚本和文档。
- 浅色紧凑布局、固定业务导航和全局状态条；默认商家池，支持 URL 片段切换。
- 商家列表与详情分开，详情增加目录/备注标签/来源视图；候选信息与审核操作分列，时间显示为北京时间。
- 本地打包 Lucide 图标，异步状态恢复保留图标，页面移除外部字体依赖。
- 验证：80 项后端回归测试通过；前端与验收脚本语法、差异检查通过；临时数据库浏览器验收全部五个页面的桌面/移动布局、商家目录流程和候选审核，截图及页面宽度检查通过。
- 后端接口和数据库结构未改动；T2 候选来源及规则仍需独立分支实现。

## 补货阶段 T1.1 — 手动添加商家（2026-10-02）

- 分支：`codex/t1-manual-seller`。
- 新增 `POST /api/pool`、`radar pool add` 和商家池添加表单；接受正整数商家 ID 或闲鱼 `/personal?userId=` 链接。
- 独立记录 `manual` 来源，重复添加去重，保留已有昵称及暂停/停止状态；添加不触发在线采集。
- 验证：77 项回归测试通过，JavaScript 语法检查通过；临时数据库 Playwright 验证添加、暂停后重复添加、错误链接及桌面/移动截图。
- 本块不含备注标签和目录改进，它们各用独立分支继续实现。

## 补货阶段 T1.2 — 商家备注和标签（2026-10-02）

- 分支：`codex/t1-seller-notes-tags`。
- v5 迁移为商家新增 `notes/tags`；旧数据默认空值，原监控状态和来源保留。
- 新增 `PATCH /api/pool/{seller_id}/metadata`，商家详情编辑备注标签，列表展示标签；标签清洗去重并限制数量和长度。
- 验证：78 项回归测试、JavaScript 和差异检查通过；临时数据库浏览器验证保存、重载、重复添加仍保留备注标签及桌面/移动截图。

## 补货阶段 T1.3 — 商家目录筛选与扫描提示（2026-10-02）

- 分支：`codex/t1-catalog-filters`。
- 商家详情 API 和 Web 支持标题子串搜索、商品状态筛选，分页总量与过滤结果一致；搜索特殊字符不当通配符。
- 同时返回并展示最近扫描、最近成功完整扫描；失败扫描不会掩盖旧目录的时间和范围。
- 验证：38 项相关回归测试、JavaScript 和差异检查通过；临时数据库浏览器验证两页目录、搜索/状态组合、失败提示及桌面/移动截图。

## 补货阶段 T1.4 — 店铺主图保存和展示（2026-10-02）

- 分支：`codex/t1-catalog-images`。
- v6 迁移为商品当前态和快照新增主图 URL；沿现有完整扫描写入，目录 API 返回主图。
- Web 增加固定尺寸缩略图、无图和链接失效状态，移动端表格仅在自身容器横向滚动；更新静态资源版本。
- 验证：80 项全量测试通过，包括主图更新/快照、不完整扫描保护和旧数据默认值；JavaScript 与差异检查通过，浏览器验证主图加载/失效/缺失及桌面/移动截图、页面宽度。
- T1 完成。T0 的真实业务样本仍待补充；后续 T2 需独立实现候选来源和筛选规则，不能把当前目录能力视为补货闭环完成。

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

## Phase 6 — 候选概览（2026-09-28）

- 候选 API 增加审核状态筛选，以及按时间和数据质量汇总的候选总量、各状态数量、多商家出现数量。
- Web 候选页展示概览并支持状态筛选；统计只使用本地候选记录，不新增闲鱼请求或数据库字段。
- 离线自动测试 58 项通过，`node --check web/app.js` 通过。

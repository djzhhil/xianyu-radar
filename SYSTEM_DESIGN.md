# SYSTEM_DESIGN.md

> Phase 2：基于 `PROJECT_ANALYSIS.md` 的自有系统设计。  
> **本阶段仍不大规模编码。** 目标是把业务链落成清晰模块、数据模型与 MVP 边界。

工作区：`/root/projects/xianyu-radar/`（研究材料只读：`_research/`）

---

## 1. 系统一句话

**xianyu-radar** 帮助商家从「已验证能卖的关键词」出发，发现同类卖家，持续观察其商品行为，并把「非目标品类上新」沉淀为候选选品，供人工小规模实验验证。

```text
发现 ≠ 上架 ≠ 有效商品
成交 = 验证
```

技术只是这条实验循环的工具。

---

## 2. 架构总览

```text
                    ┌──────────── auth ────────────┐
                    │  Cookie / _m_h5_tk / 暂停旗标  │
                    └──────────────┬───────────────┘
                                   │
┌──────────┐   seed items    ┌─────▼──────┐   seller_ids   ┌─────────────┐
│ discovery│ ───────────────►│  sellers   │ ─────────────►│   items     │
│  search  │                 │ seller_pool│   scan jobs   │ repository  │
│  parse   │                 │  fetcher   │               │ history     │
│  seller  │                 │  monitor   │               │ diff        │
└──────────┘                 └─────┬──────┘               └──────┬──────┘
                                   │                             │
                                   │ NEW_ITEM events             │
                                   └─────────────┬───────────────┘
                                                 ▼
                                         ┌─────────────┐
                                         │ candidates  │
                                         │ detector    │
                                         │ repository  │
                                         └─────────────┘
                                                 ▲
┌────────────┐                                   │
│ scheduler  │ ── 驱动 discovery / seller scan ──┘
└─────┬──────┘
      │
┌─────▼──────┐
│  storage   │  SQLite（唯一事实源）
└────────────┘
      │
┌─────▼──────┐
│    cli     │  无 GUI（MVP）
└────────────┘
```

### 设计原则（来自研究）

| 原则 | 来源 | 落地 |
|------|------|------|
| 搜索与店铺监控分离 | Asher 缺后半、zpl11 缺前半 | `discovery` ⊥ `sellers` |
| sellerId 一级实体 | 两边都弱 | `sellers` 表 + pool 入池记录 |
| itemId 商品身份 | zpl11 | `items.item_id` PK |
| snapshot/diff 才能得事件 | zpl11 | `item_snapshots` + `item_events` |
| 发现与价值判断分离 | Asher AI 应后置；我们业务 | Candidate 只入池，不自动上架 |
| 浏览器最小化 | zpl11 演进结论 | auth 可浏览器；列表 HTTP |
| 失败 ≠ 全店下架 | zpl11 checkCount | diff 保护规则 |
| 慢比快重要 | 业务长期跑 | scheduler 抖动/退避 |

---

## 3. 目录结构（建议）

不强制与用户草案逐字一致；职责对齐即可。

```text
xianyu-radar/
├── PROJECT_ANALYSIS.md          # Phase 1
├── SYSTEM_DESIGN.md             # Phase 2（本文件）
├── IMPLEMENTATION_PLAN.md       # Phase 3
├── _research/                   # 只读参考仓库（不改）
├── pyproject.toml / requirements.txt
├── README.md
├── data/                        # runtime：sqlite、state（gitignore）
│   ├── radar.sqlite3
│   └── state/                   # cookies / session json
├── src/xianyu_radar/
│   ├── __init__.py
│   ├── config.py                # 路径、间隔、APP_KEY 等
│   ├── auth/
│   │   ├── session.py           # 加载/校验 cookie、token
│   │   └── mtop.py              # 签名 + call_mtop
│   ├── discovery/
│   │   ├── keyword_search.py    # search(keyword) → list[SeedItem]
│   │   ├── item_parser.py       # 解析列表/详情字段
│   │   └── seller_discovery.py  # SeedItem → seller_id 入池
│   ├── sellers/
│   │   ├── pool.py              # SellerPool CRUD / 入池动机
│   │   ├── fetcher.py           # get_seller_items(seller_id)
│   │   └── monitor.py           # 扫描一个卖家：fetch → diff → 写库
│   ├── items/
│   │   ├── repository.py
│   │   ├── history.py           # snapshot 追加
│   │   └── diff.py              # current vs previous → events
│   ├── candidates/
│   │   ├── detector.py          # NEW_ITEM → 是否候选
│   │   ├── score.py             # MVP：seller_count 等简单分
│   │   └── repository.py
│   ├── storage/
│   │   ├── db.py                # 连接、迁移
│   │   └── schema.sql
│   ├── scheduler/
│   │   └── runner.py            # 轮询池、抖动、退避
│   └── cli.py                   # 入口命令
└── tests/
    ├── test_diff.py
    ├── test_candidate_detector.py
    └── fixtures/                # 脱敏的 API JSON 样例
```

语言选择：**Python 3.11+**（与 Asher 同栈，便于对照 parsers；MTOP 签名逻辑从 zpl11 移植为 Python）。CLI 用 `argparse` 或 `typer`。

---

## 4. 模块职责

### 4.1 `auth`

- 从 `data/state/*.json` 加载 Cookie；
- 解析 `_m_h5_tk` → sign token；
- `call_mtop(api, data, extra_params)`；
- 会话失效 / 风控：置 `auth_status=paused`，调度器跳过网络任务并提示。

**启发：** zpl11 `createSign`/`callMTOP`；Asher 的 state 文件外置。  
**重设计：** 统一 session 模块，不绑 Web UI；MVP 可不内嵌 CDP（Cookie 可手工/扩展导入）。

### 4.2 `discovery`

| 函数 | 输入 | 输出 |
|------|------|------|
| `search(keyword, **filters)` | 关键词 | `SeedItem[]`（item_id, title, price, url, seller_nick?） |
| `enrich_seller_id(item)` | SeedItem | seller_id（必要时打 detail） |
| `discover_sellers(keyword)` | 关键词 | 写入 items（seed）+ seller_pool |

**启发：** Asher 搜索→详情→sellerId 链。  
**重设计：** 先尝试 MTOP 直签搜索；若不稳定，再加 Playwright 拦截适配器，接口不变。  
**不做：** AI 推荐、通知、硬过滤大而全（MVP 只保留可选价格区间等最小过滤）。

### 4.3 `sellers`

| 组件 | 职责 |
|------|------|
| `pool` | 入池、去重、记录来源关键词/商品、启用/暂停 |
| `fetcher` | `get_seller_items(seller_id)` 分页拉全量在售 |
| `monitor` | 对单个卖家：fetch → diff → 更新 items → 产出 events |

**启发：** zpl11 `idle.web.xyh.item.list` + syncItems。  
**重设计：** 多卖家池 + SQLite；不是单店 JSON。

### 4.4 `items`

| 组件 | 职责 |
|------|------|
| `repository` | 当前态 Item upsert |
| `history` | 每次成功扫描写 snapshot（或至少在字段变化时写） |
| `diff` | `NEW_ITEM` / `REMOVED_ITEM` / `PRICE_CHANGED` / `TITLE_CHANGED` |

保护规则（必须）：

1. 本次列表为空或明显异常 → **不产生 REMOVED**，记 `scan_failed`；
2. 卖家首次成功扫描 → 全量建档，事件标记 `baseline=true`（不进入候选，或候选引擎忽略 baseline）；
3. 身份键 = `item_id`（字符串）。

### 4.5 `candidates`

| 组件 | 职责 |
|------|------|
| `detector` | 非 baseline 的 `NEW_ITEM` → 判断是否「原始目标商品」 |
| `score` | MVP：`seller_count`、`appearance_count`；可后续加权 |
| `repository` | 候选 CRUD；status 机 |

**「是否原始关键词对应商品」MVP 策略（简单可测）：**

1. 标题归一化后包含监控任务的 `keyword`（或用户配置的 `exclude_patterns` / `seed_title_tokens`）→ 视为目标同类，**不入候选**；
2. 否则入候选；
3. 同一归一化标题跨卖家出现 → 合并 `source_sellers`，增加 `seller_count`。

第二阶段再引入更复杂的相似度；MVP 不接 AI。

### 4.6 `scheduler`

- 队列：discovery 任务（低频）与 seller scan（按池轮转）；
- 间隔：基础 interval + 随机抖动；
- 错误：指数退避；连续 N 次 auth/风控 → 全局暂停；
- 单卖家 `is_scanning` 锁，防重入；
- CLI：`radar run` 前台循环；`radar scan-once` 单次。

### 4.7 `storage`

唯一事实源 SQLite：`data/radar.sqlite3`。  
迁移用简单 `schema_version` 表。

### 4.8 `cli`（MVP 命令）

```text
radar auth check
radar discover --keyword "..."
radar pool list
radar pool enable|pause SELLER_ID
radar scan-seller SELLER_ID
radar scan-pool                 # 扫一遍启用中的卖家
radar candidates [--since 24h]
radar events [--seller ...] [--since ...]
radar run                       # 调度循环
```

---

## 5. 数据模型

### 5.1 表设计（第一版）

#### `sellers`

| 列 | 说明 |
|----|------|
| seller_id TEXT PK | 闲鱼 userId |
| nickname TEXT | 可空，可更新 |
| first_seen_at |
| last_seen_at |
| last_scan_at |
| status | `watching` / `paused` / `dropped` |
| consecutive_failures INT | 退避用 |

#### `seller_pool_entries`（入池动机，可多条）

| 列 | 说明 |
|----|------|
| id INTEGER PK |
| seller_id FK |
| source_keyword |
| source_item_id |
| reason TEXT | 如 `discovered_via_keyword` |
| joined_at |
| active INTEGER | 是否仍作为入池依据 |

同一 seller 可被多个关键词发现；监控以 `sellers.status` 为准。

#### `items`

| 列 | 说明 |
|----|------|
| item_id TEXT PK |
| seller_id FK |
| title |
| price TEXT | 与 API 一致先存文本，展示再格式化 |
| url |
| category TEXT | MVP 可空 |
| status | `active` / `removed` / `unknown` |
| first_seen_at |
| last_seen_at |
| last_price |
| last_title |
| check_count INT | 成功扫描命中次数 |
| source | `discovery` / `seller_scan` |

#### `item_snapshots`

| 列 | 说明 |
|----|------|
| id INTEGER PK |
| item_id |
| seller_id |
| title |
| price |
| captured_at |
| scan_id | 同一次扫描批次 |

#### `item_events`

| 列 | 说明 |
|----|------|
| id INTEGER PK |
| item_id |
| seller_id |
| event_type | `NEW_ITEM` / `REMOVED_ITEM` / `PRICE_CHANGED` / `TITLE_CHANGED` |
| old_value / new_value | JSON 或短文本 |
| is_baseline INTEGER | 首次建档 |
| detected_at |
| scan_id |

唯一性：不对事件做强 UNIQUE；靠状态机避免重复写入（diff 层）。

#### `discovery_runs`

| 列 | 说明 |
|----|------|
| id | scan/run id |
| keyword |
| started_at / finished_at |
| item_count / seller_count |
| status | ok / failed |

#### `candidates`

| 列 | 说明 |
|----|------|
| candidate_id INTEGER PK | 或用 hash(normalized_title) |
| normalized_title |
| sample_item_id | 代表性 item |
| sample_title / sample_price / sample_url |
| first_seen_at |
| last_seen_at |
| seller_count |
| appearance_count |
| score REAL |
| status | `new` / `watching` / `testing` / `validated` / `rejected` |

#### `candidate_sellers`（多对多）

| candidate_id | seller_id | first_item_id | first_seen_at |

#### `watch_keywords`（可选 MVP）

| keyword PK | exclude_patterns JSON | created_at | enabled |

#### `meta`

| key | value | 如 schema_version、auth_paused |

### 5.2 为何这样建模

| 决策 | 原因 |
|------|------|
| Seller 与 Item 分表 | 商家是信息源，商品是观察对象 |
| pool_entries 与 sellers 分离 | 「为何入池」可审计，暂停监控不丢动机史 |
| snapshots + events | 可回溯行为；events 服务候选与 CLI |
| candidates 按归一化标题聚合 | 回答「多少卖家在卖类似新货」 |
| price 存 TEXT | 与平台字符串一致，避免解析坑；后续再规范化 |
| 不用每店一个 JSON | 要跨卖家查询「24h 上新」 |

---

## 6. 数据流（MVP 闭环）

### Step 1–3：发现 → 入池

```text
CLI: radar discover --keyword K
  → auth.check()
  → discovery.search(K)
  → 对每个结果 enrich seller_id（详情如需要）
  → upsert items (source=discovery)
  → upsert sellers + seller_pool_entries
  → 打印：商品数、新入池卖家数
```

### Step 4–6：扫描 → snapshot → diff

```text
CLI: radar scan-seller S  /  radar scan-pool
  → fetcher.get_seller_items(S)
  → 若空/失败：记 failure，不 diff 下架
  → 若该卖家从未成功扫描：baseline upsert，events.is_baseline=1
  → 否则 diff.py：
        新 id → NEW_ITEM
        缺 id → REMOVED_ITEM（check_count 规则）
        价/题变 → PRICE/TITLE_CHANGED
  → 写 item_snapshots、更新 items、写 item_events
  → 更新 sellers.last_scan_at
```

### Step 7–8：候选

```text
对非 baseline 的 NEW_ITEM：
  → detector：命中关键词/排除规则？ → 忽略
  → 否则 upsert candidates + candidate_sellers
  → score 更新

CLI: radar candidates --since 24h
  → 按 score/seller_count 列出
```

---

## 7. 调度与状态

### 卖家状态

```text
watching ──(手动/连续失败)──► paused ──(手动/auth恢复)──► watching
    │
    └──(手动)──► dropped   （不再扫描，保留历史）
```

### 候选状态（MVP 只自动写 `new`）

```text
new → watching → testing → validated
                         ↘ rejected
```

`testing/validated/rejected` 第二阶段人工流转；MVP CLI 可预留 `radar candidate set-status`。

### 扫描状态

每次 `scan_id`：`running` → `ok` | `failed`。  
失败原因分类：`auth` / `rate_limit` / `empty` / `parse` / `network`。

---

## 8. 错误处理与风控

| 场景 | 行为 |
|------|------|
| Cookie 失效 | 全局 `auth_paused`；CLI 明确提示；不空扫导致假下架 |
| `FAIL_SYS_USER_VALIDATE` | 该次失败；退避；可选「请浏览器刷新」提示；MVP 不自动打码 |
| 列表空 | 不 REMOVED；`consecutive_failures++` |
| 单卖家连续失败 | 自动 `paused`，人工检查 |
| 解析异常 | 保留 raw 响应到 `data/debug/`（限数量），失败该卖家本轮 |
| 请求频率 | 默认卖家间隔数十秒级 + 抖动；关键词发现更低频 |

---

## 9. MVP 边界

### 做

- 关键词发现 → seller pool
- `get_seller_items` + snapshot/diff
- 候选池 + 近 24h 查询
- SQLite + CLI
- 基础 auth 加载与暂停

### 不做

- Web GUI / AI 选品 / 通知风暴
- 自动上架 / 购买 / 发货
- 五维统计（浏览想要等）强依赖
- 多账号复杂轮换（可留接口）
- 安卓/MCP
- 修改 `_research/` 原项目

### 验收口径（对应用户第十一节）

```text
输入关键词 A
  → 找到商品并保存 itemId/title/price/sellerId/url
  → 建立 seller pool
  → 扫描卖家商品并保存首次状态（baseline）
  → 再次扫描能产出 NEW_ITEM 等事件
  → 非目标类 NEW 进入 candidates
  → radar candidates --since 24h 给出列表（含来源卖家数）
```

---

## 10. 启发归属

| 能力 | 启发自 | 我们的重设计 |
|------|--------|--------------|
| 关键词搜索字段与详情取 sellerId | Asher | 独立 `discovery`；Seller 一级表 |
| 登录态文件 | Asher | 无 Web 账号后台；纯文件 + CLI |
| 硬过滤思想 | Asher | MVP 极简；候选阶段再排除 |
| MTOP 签名 + 店铺列表 | zpl11 | Python 重写；多卖家池 |
| snapshot/diff 事件 | zpl11 | SQLite events；baseline 标记 |
| checkCount / 空列表保护 | zpl11 | 写入 `items.diff` 硬规则 |
| 浏览器仅 auth | zpl11 | MVP 甚至可无 CDP（外置 cookie） |
| Seller Pool / Candidate / 实验边界 | **原创** | 业务核心 |
| 「排除原关键词商品」 | **原创** | detector 规则 |

---

## 11. 风险与开放问题

1. **搜索是否能稳定直签？**  
   若否，discovery 适配器改为 Playwright 拦截，sellers 监控仍走 HTTP。

2. **搜索列表是否偶发带 userId？**  
   有则减少 detail 调用；无则保持详情补全。

3. **标题编码抖动导致假 TITLE_CHANGED？**  
   diff 前统一 Unicode 正规化；必要时空格折叠。

4. **平台 API/APP_KEY 变更**  
   配置化；fixtures 回归。

5. **法律与 ToS / 账号安全**  
   低频、自用、不爆破；风控即停。

---

## 12. Phase 2 → Phase 3

下一步产出 `IMPLEMENTATION_PLAN.md`，将实现拆为可独立验收的 Task 01…N（schema → search → sellerId → pool → fetch → snapshot → diff → candidates → scheduler），每项含目标/输入/输出/文件/验收/风险。

仍不一次性生成整仓业务代码。

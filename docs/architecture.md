# 代码地图：五条业务路线

把目录当作地图看：`entrypoints/api/routes/` 是用户进入项目的门，`modules/` 是五块业务区域，`infrastructure/` 是各区域共用的通道与仓库工具。目录在磁盘上同级，并不表示运行时也同级：请求由 API 入口进入业务模块，业务模块使用基础设施，最后返回结果。

## 第一层：项目区域

| 位置 | 用途 |
| --- | --- |
| `README.md` | 安装、运行、常用命令和项目边界。 |
| `pyproject.toml` | Python 依赖、打包、`radar` 与 `radar-web` 命令配置。 |
| `src/xianyu_radar/` | Python 程序源码。 |
| `web/` | 浏览器页面：`index.html` 页面结构、`styles.css` 样式、`app.js` 发 HTTP 请求并展示结果。 |
| `tests/` | 自动测试；`fixtures/` 是离线闲鱼响应样本。 |
| `scripts/` | 手动冒烟步骤。 |
| `docs/` | 当前代码地图和登录态格式说明。 |
| `data/` | 唯一的运行数据目录：`radar.sqlite3` 数据库、`state/` 登录态和 `debug/` 调试文件；不属于源码。 |
| `PROJECT_ANALYSIS.md`、`SYSTEM_DESIGN.md`、`IMPLEMENTATION_PLAN.md`、`PROGRESS.md` | 项目分析、早期设计、实施计划和进度记录；具体代码位置以本文为准。 |

## 第二层：源码区域

```text
src/xianyu_radar/
├── entrypoints/
│   ├── api/                    HTTP 入口：注册、分发、请求校验、响应转换
│   │   ├── app.py              FastAPI 应用，挂载 web/，注册路由
│   │   ├── server.py           Web 服务启动
│   │   ├── deps.py             数据库连接、会话、时间和事件响应辅助函数
│   │   └── routes/             按 HTTP 地址分发到业务模块
│   └── cli.py                  radar 命令入口；与 API 是并列入口
├── modules/                     五个业务模块；service.py 是各模块对外的主入口
│   ├── auth/                    保存、查看和检查登录态
│   ├── discovery/               搜索商品、发现卖家并入池
│   ├── pool/                    查看商家池、修改商家状态
│   ├── scan/                    扫描商家、比较变化、生成事件和候选
│   └── candidates/              查看候选商品、修改审核状态
├── infrastructure/              多条业务链路共用的技术能力
│   ├── goofish/                闲鱼会话解析与 MTOP 请求
│   ├── storage/                SQLite 连接、schema、商家数据和认证暂停状态
│   └── item_identity.py        商品 ID 与 URL 的统一规则
├── config.py                    数据路径和扫描参数
├── models.py                    业务链路传递的数据结构
└── __init__.py                  包版本
```

各目录的 `__init__.py` 让 Python 识别包，通常不是业务入口。

### HTTP 门牌与业务入口

| 路由文件 | 用户功能 | 进入的业务模块 |
| --- | --- | --- |
| `routes/auth.py` | 登录态状态、保存、检查、解除暂停 | `auth/service.py` |
| `routes/discover.py` | 按关键词发现商家 | `discovery/service.py` |
| `routes/pool.py` | 查看商家池、改变商家状态 | `pool/service.py` |
| `routes/scan.py` | 扫描单个商家或整个商家池 | `scan/service.py`、`scan/runner.py` |
| `routes/events.py` | 查看扫描产生的商品事件 | `scan/service.py` |
| `routes/candidates.py` | 查看候选、改变候选审核状态 | `candidates/service.py` |
| `routes/status.py` | 健康检查与系统概览 | 系统查询 |

`routes/` 按 HTTP 地址分文件，`modules/` 按业务能力分文件。这是两种不同维度：门牌负责接请求，业务区负责完成工作。

Web 页面按这五块业务区显示五个步骤：登录态、发现商家、商家池、扫描商家、候选商品。发现页显示本次搜索商品和最近发现记录；商家池可打开商家详情、入池来源和已存商品；扫描页显示最近扫描记录与事件前后值；候选页显示价格、商品链接、发现时间和审核状态。商品、事件和候选列表按页读取。扫描产生的事件在“扫描商家”页查看；“扫描全部”和“扫描单个”共用一个扫描入口，通过选择范围区分。

这些展示只读本地 SQLite。对应查询入口是 `GET /api/discover/runs`、`GET /api/pool/{seller_id}`、`GET /api/scan/runs`、`GET /api/events` 和 `GET /api/candidates`；打开页面不会请求闲鱼。点击“开始发现”或“开始扫描”才进入在线流程。

### 五块业务区内部

| 目录 | 文件与职责 |
| --- | --- |
| `auth/` | `service.py`：登录态查看、保存、检查 MTOP 连通性、清除认证暂停。 |
| `discovery/` | `service.py`：发现流程编排、写入发现记录和种子商品；`keyword_search.py`：调用搜索接口；`item_parser.py`：解析搜索结果、提取卖家信息。 |
| `pool/` | `service.py`：商家列表与状态修改的业务入口。实际商家表读写由共用的 `infrastructure/storage/seller_repository.py` 完成。 |
| `scan/` | `service.py`：单商家扫描、落库和事件生成；`runner.py`：逐个扫描商家池及循环调度；`fetcher.py`：拉取店铺商品；`shop_parser.py`：解析店铺列表；`diff.py`：比较前后商品；`item_repository.py`：商品当前态读写；`history.py`：写快照、查扫描记录；`events.py`：查询变化事件；`candidate_detector.py`：根据新商品事件生成候选。 |
| `candidates/` | `service.py`：候选列表与状态修改入口；`repository.py`：候选表查询、状态更新。 |

`infrastructure/goofish/session.py` 从 Cookie JSON 建立会话；`mtop.py` 计算签名并访问闲鱼接口。`infrastructure/storage/db.py` 连接和初始化 SQLite，`schema.sql` 定义表，`seller_repository.py` 读写商家池相关表，`auth_state.py` 管理认证暂停标志。发现和扫描都需要闲鱼协议；发现、商家池和扫描都需要访问商家数据，所以这些代码放在共用区域。

## 第三层：用户进入后会发生什么

```mermaid
flowchart LR
  User[浏览器操作] --> API[entrypoints/api/routes]
  API --> Auth[auth/service.py]
  API --> Discover[discovery/service.py]
  API --> Pool[pool/service.py]
  API --> Scan[scan/service.py 或 runner.py]
  API --> Candidate[candidates/service.py]
  Discover --> Infra[infrastructure]
  Auth --> Infra
  Pool --> Infra
  Scan --> Infra
  Candidate --> DB[(SQLite)]
  Infra --> DB
```

箭头表示代码调用方向。五个 `modules/` 子目录之间没有直接 Python 导入。它们可以读写同一个 SQLite 数据库：例如发现把商家入池，后来的扫描再从池中读取；扫描写出候选，候选模块后来读取。这是**通过数据衔接业务流程**，不是 `discovery.py` 直接调用 `scan.py`。

### 1. 保存或检查登录态

`web/app.js` → `routes/auth.py` → `auth/service.py` → `infrastructure/goofish/session.py` 解析 Cookie；需要在线检查时再由 `infrastructure/goofish/mtop.py` 发请求。保存的会话文件在 `data/state/`，认证暂停标志在 SQLite 的 `meta` 表。

### 2. 发现商家

`web/app.js` → `routes/discover.py` → `discovery/service.py` → `keyword_search.py` → `item_parser.py`。搜索使用共用的 MTOP 客户端。解析器从搜索结果中读取明确的数字卖家 ID，也从商品图片地址提取数字候选值。图片候选值只在当前搜索结果中没有跨卖家复用、同一卖家没有多个不同候选值时作为卖家 ID 使用；这一步只检查内存中的搜索结果，不请求商家商品列表。同一搜索卖家的其他商品可关联到这个 ID。仍未识别的商品沿用详情接口补全；遇到人机验证时，如果已有识别的商家，就保留这些商家并在响应中标明 `validation_required`，否则返回 403。无法识别卖家的搜索结果计入 `skipped_no_seller`。本步不调用扫描模块。

### 3. 管理商家池

`routes/pool.py` → `pool/service.py` → `storage/seller_repository.py` → SQLite。查看 `watching` 商家或修改商家状态，都在这一条链里完成。

### 4. 扫描商家

单商家：`routes/scan.py` → `scan/service.py` → `fetcher.py`/`shop_parser.py` 拉取并解析商品 → `item_repository.py` 读取旧商品 → `diff.py` 比较 → `item_repository.py`、`history.py` 保存当前态和快照 → `service.py` 写 `item_events` → `candidate_detector.py` 从非基线 `NEW_ITEM` 中写候选。结果存入 `scans`、`items`、`item_snapshots`、`item_events`、`candidates` 等表。

商家池：`routes/scan.py` → `scan/runner.py` → 共用的商家仓库读取 `watching` 商家 → 对每个商家调用同模块的 `scan/service.py`。循环调度也是 `runner.py`，并由 CLI 触发。

自动测试用 `tests/fixtures/` 的样本模拟闲鱼响应，在临时数据库中验证解析和扫描；对外 API 只使用当前会话发起真实请求。发现阶段已有种子商品时，第一次店铺扫描不一定是完整基线；这取决于库里是否已有该商家的商品当前态。

### 5. 查看候选与事件

候选：`routes/candidates.py` → `candidates/service.py` → `candidates/repository.py` → `candidates`、`candidate_sellers` 表。事件：`routes/events.py` → `scan/service.py` → `scan/events.py` → `item_events` 表。这里读取先前扫描写出的结果，没有反向调用扫描执行流程。

## 阅读顺序

想追一个功能时，先找对应 `routes/*.py`，再进入该业务模块的 `service.py`，顺着其导入和函数调用往下看，最后看 `infrastructure/` 和 SQLite 表。不要只按目录上下位置猜调用方向；以函数调用和导入为准。

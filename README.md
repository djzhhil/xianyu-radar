# xianyu-radar

从**已验证能卖的商品关键词**出发：搜索闲鱼 → 发现卖家 → 建立商家池 → 持续扫描店铺商品 → snapshot/diff → 把非目标上新放入**候选选品池**，供人工小规模实验。

```text
发现 ≠ 上架 ≠ 有效商品
成交 = 验证
```

研究材料（只读）：`_research/xianyu-monitor`、`_research/xianyu-automation`  
设计文档：`PROJECT_ANALYSIS.md` → `SYSTEM_DESIGN.md` → `IMPLEMENTATION_PLAN.md` → `PROGRESS.md`

当前代码的目录地图与请求链路：[`docs/architecture.md`](docs/architecture.md)。设计文档记录早期方案，路径以当前代码地图为准。

数据可信度问题的定位、文件级修复步骤和验收标准：[`docs/repair_plan.md`](docs/repair_plan.md)。

## 安装

```bash
cd /root/projects/xianyu-radar
python3 -m venv .venv
source .venv/bin/activate
# 若环境有坏掉的 HTTP 代理，先 unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
pip install -e ".[dev]"
radar init-db
pytest -q
```

## Web UI（前后端联调）

```bash
radar serve --host 127.0.0.1 --port 8765
# 打开 http://127.0.0.1:8765
# API 文档 http://127.0.0.1:8765/docs
```

真实扫描需要在「登录态」粘贴含 `_m_h5_tk` 的 Cookie（不要用 `tokensecret` 测试占位）。
如果发现时提示闲鱼人机验证，请先在浏览器完成验证并更新 Cookie；未取得真实数字卖家 ID 的搜索商品不会进入商家池。

数据目录：

```text
data/radar.sqlite3       # 唯一的业务数据库
data/state/default.json  # 登录态
data/debug/               # 调试文件
```

从旧版升级时，将原 `data/prod/radar.sqlite3` 和 `data/prod/state/` 中的文件移到上述位置；不要覆盖已经存在的目标文件。本工作区的数据已完成迁移。

数据库初始化会按版本升级；升级前请备份 `data/radar.sqlite3`。本工作区的 v1 备份存于 `data/backups/`。修复前的候选标为 `legacy_unverified`，在 Web 候选页或 `radar candidates --quality legacy_unverified` 中复核；人工审核状态仍保留。

Web 候选页可按时间、数据质量和审核状态筛选；概览统计当前时间及质量范围内的候选总量、待复核数、多商家出现数和已验证数。概览基于已保存的候选记录，不代表闲鱼浏览量或想要数。

## 登录态

将 Cookie 放到 `data/state/default.json`（见 `docs/session_format.md`）。
必须包含 `_m_h5_tk`。也可在 Web「登录态」页粘贴保存。

```bash
radar auth check
# 可选真实探测：
radar auth check --ping
```

## 主流程 CLI

```bash
# 1) 关键词发现 → 商家池（在线）
radar discover --keyword "你的已验证商品名" --max-pages 3
# 中断后按原关键词继续；可调高总页数上限
radar discover --keyword "你的已验证商品名" --resume-run-id <runId> --max-pages 5

# 2) 查看商家池
radar pool list
radar pool add 'https://www.goofish.com/personal?userId=123456' --nickname '重点商家'
radar pool set-status <sellerId> paused|watching|dropped

# 3) 扫描（是否为 baseline 取决于该卖家已有的商品记录）
radar scan-seller <sellerId>
radar scan-pool

# 4) 再次扫描后查看候选 / 事件
radar candidates --since 24h
radar candidates --quality normal --since 24h
radar events --since 24h

# 5) 长期轮询（慢速 + 抖动）
radar run --interval 90 --jitter 30
```

自动测试与手动验证步骤：`scripts/mvp_smoke.md`

发现按页保存进度。Web 的「最近发现记录」区分原始结果、去重商品、识别商家和新增商家；「查看诊断」可查每页及每件商品的处理结论，「继续」会从未完成页和待补全商品恢复。接口分别是 `GET /api/discover/runs/{run_id}` 和 `POST /api/discover`（传入 `resume_run_id` 与原关键词）。诊断只保存字段名、计数、状态及按运行 ID 散列的商品引用，不保存原始搜索/详情响应和 Cookie。限流或人机验证会立即停止后续请求，并保留已确认的商家。

店铺扫描以 `nextPage`、短页和有效的正数 `totalCount` 判断结束；有商品时返回的 `totalCount=0` 视为不可用。没有明确结束信号的空页、重复页、页数上限或总数不一致仍记为不完整，不能改动商品当前态、事件和候选。`GET /api/scan/runs/{scan_id}` 可查脱敏的每页计数与分页信号。已确认的空店和商品数骤降仍需要第二次完整扫描才能确认。

## 代码区域

| 区域 | 职责 |
|----|------|
| `src/xianyu_radar/entrypoints/` | HTTP API 和 CLI 入口 |
| `src/xianyu_radar/modules/` | 按业务能力划分的模块 |
| `src/xianyu_radar/infrastructure/` | 各业务共用的闲鱼协议、商品标识规则与 SQLite 存储 |

### 业务模块

| 包 | 职责 |
|----|------|
| `auth` | 登录态保存、状态和检查 |
| `discovery` | 关键词搜索、解析结果、发现商家并入池 |
| `pool` | 查看商家池、修改商家状态 |
| `scan` | 拉取店铺商品、比较变化、保存事件和候选、轮询商家池 |
| `candidates` | 查看候选商品、修改审核状态 |

每个业务目录的 `service.py` 是该功能的主入口。API 路由位于 `entrypoints/api/routes/`，按 HTTP 地址分发；业务模块之间没有直接 Python 导入。完整目录地图和请求链路见 [`docs/architecture.md`](docs/architecture.md)。

## MVP 边界

**做了：** 发现→池→扫描→diff→候选→CLI、Web UI、SQLite；首次扫描基线、分页完整性和异常数量复扫保护
**不做：** AI、自动上架/购买/发货、五维统计强依赖

## 测试

```bash
pytest -q
```

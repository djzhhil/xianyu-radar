# xianyu-radar

从**已验证能卖的商品关键词**出发：搜索闲鱼 → 发现卖家 → 建立商家池 → 持续扫描店铺商品 → snapshot/diff → 把非目标上新放入**候选选品池**，供人工小规模实验。

```text
发现 ≠ 上架 ≠ 有效商品
成交 = 验证
```

研究材料（只读）：`_research/xianyu-monitor`、`_research/xianyu-automation`  
设计文档：`PROJECT_ANALYSIS.md` → `SYSTEM_DESIGN.md` → `IMPLEMENTATION_PLAN.md` → `PROGRESS.md`

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
radar serve --host 127.0.0.1 --port 8765 --env prod
# 打开 http://127.0.0.1:8765
# API 文档 http://127.0.0.1:8765/docs
```

右上角可切换 **prod**（真实） / **demo**（离线夹具库）。

- 无真实 Cookie：切到 demo，点 **「离线闭环 → 只写 demo 库」**
- 真实扫描：在 prod 的「登录态」粘贴含 `_m_h5_tk` 的 Cookie（不要用 `tokensecret` 测试占位）

数据目录：

```text
data/prod/   # 真实运行
data/demo/   # 离线 Demo
```

首次隔离旧扁平数据：

```bash
radar env isolate
```

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
radar discover --keyword "你的已验证商品名"

# 2) 查看商家池
radar pool list
radar pool set-status <sellerId> paused|watching|dropped

# 3) 扫描（首次为 baseline，不进候选）
radar scan-seller <sellerId>
radar scan-pool

# 4) 再次扫描后查看候选 / 事件
radar candidates --since 24h
radar events --since 24h

# 5) 长期轮询（慢速 + 抖动）
radar run --interval 90 --jitter 30
```

离线/夹具：`scripts/mvp_smoke.md`

## 模块

| 包 | 职责 |
|----|------|
| `auth` | Cookie / MTOP 签名 |
| `discovery` | 关键词搜索、解析、sellerId |
| `sellers` | 商家池、拉店、监控 |
| `items` | 当前态、snapshot、diff |
| `candidates` | 非目标 NEW → 候选 |
| `scheduler` | 轮询 / 退避 |
| `storage` | SQLite |

## MVP 边界

**做了：** 发现→池→扫描→diff→候选→CLI+SQLite  
**不做：** GUI、AI、自动上架/购买/发货、五维统计强依赖

## 测试

```bash
pytest -q
```

# PROJECT_ANALYSIS.md

> Phase 1 研究成果。仅分析 `_research/` 下两个参考仓库，**不实现正式业务系统**。  
> 研究材料路径：
>
> - `_research/xianyu-monitor` ← [Asher-2000/xianyu-monitor](https://github.com/Asher-2000/xianyu-monitor)
> - `_research/xianyu-automation` ← [zpl11/xianyu-automation](https://github.com/zpl11/xianyu-automation)

---

## 0. 一句话结论

| 项目 | 在我们业务链中的位置 | 技术形态 |
|------|----------------------|----------|
| **Asher (monitor)** | **商品发现入口**：关键词 → 搜索列表 → 详情 → `sellerId` | Playwright 打开 goofish 页面，**被动拦截 MTOP 响应** |
| **zpl11 (automation)** | **商家监控核心**：`sellerId` → 全量在售商品 → snapshot/diff | Cookie + `_m_h5_tk` **主动签名调用 MTOP**；浏览器仅用于登录与 x5sec |

两者合在一起，刚好覆盖我们的主链路：

```text
已验证能卖的商品关键词
        ↓  [Asher 思想：搜索发现]
闲鱼相关商品 + sellerId
        ↓  [我们新建：Seller Pool]
持续监控商家
        ↓  [zpl11 思想：店铺列表 + snapshot/diff]
发现上新 / 下架 / 改价 / 改标题
        ↓  [我们新建：Candidate Pool]
候选选品 → 人工实验验证
```

**禁止拼接两仓库。** 下文只抽取原理与必要接口契约，后续用自有模块边界重写。

---

## 1. 业务视角：两个项目分别解决什么

### Asher 解决的问题

> 「某个关键词下，市场上出现了哪些新商品？卖家是谁？值不值得通知我？」

它是 **市场扫描器 + 结果决策器**（关键词任务、硬过滤、AI/规则推荐、通知）。  
它 **没有**「给定 sellerId，长期监控该店全部商品」的一等任务类型。卖家页爬取只是详情后的画像 enrichment。

### zpl11 解决的问题

> 「这个店铺又上了什么、下了什么、改了价/标题？」

它是 **店铺状态机**：以 `itemId` 为键保存历史，轮询列表 API 做集合差分。  
它对「从关键词发现卖家」几乎不投入；店铺 ID 靠人工输入。

### 对我们的含义

我们的假设是：

> 已验证能成交的商品 → 同类卖家 → 他们的其他商品可能也有市场价值。

因此：

- Asher 贡献 **发现卖家** 的前半段；
- zpl11 贡献 **观察卖家行为** 的后半段；
- **Seller Pool / Candidate / 排除原关键词商品类型** 是我们自己的产品层，两项目都没有。

---

## 2. 项目 A：Asher-2000/xianyu-monitor

### 2.1 项目结构（与发现相关）

| 区域 | 路径 | 角色 |
|------|------|------|
| CLI 入口 | `spider_v2.py` | 加载任务 → 调用 `scrape_xianyu` |
| 发现核心 | `src/scraper.py` | Playwright 搜索 / 详情 / 卖家页 |
| 解析 | `src/parsers.py` | 搜索 JSON、卖家头像页、在售列表、评价 |
| 分页 | `src/services/search_pagination.py` | 识别搜索 API、翻页 |
| 硬过滤 | `src/hard_filter.py` | UI 过滤失败时的二次约束 |
| 落库 | `src/services/result_storage_service.py` | 去重键 + `INSERT OR IGNORE` |
| Schema | `src/infrastructure/persistence/sqlite_connection.py` | `tasks` / `result_items` / `price_snapshots` |
| 登录导出 | `chrome-extension/` + `src/api/routes/accounts.py` | Cookie 快照 → `state/*.json` |
| 调度 | `src/services/scheduler_service.py` | APScheduler cron → 子进程跑 spider |
| **可忽略** | `web-ui/`、`src/ai_handler.py`、通知、任务生成、Dashboard | 外围 |

### 2.2 Asher 核心调用链

```text
Task.keyword
  → spider_v2.main()
  → scrape_xianyu(task_config)
  → Playwright 加载 storage_state（cookies）
  → goto https://www.goofish.com/search?q=<keyword>
  → 拦截 POST .../h5/mtop.taobao.idlemtopsearch.pc.search/1.0/
  → （可选）UI 点击：新发布 / 个人闲置 / 包邮 / 区域 / 价格
  → _parse_search_results_json → basic_items[]
  → apply_hard_filters
  → get_link_unique_key(link) 是否已见？
        未见 → goto 商品页
             → 拦截 .../h5/mtop.taobao.idle.pc.detail
             → sellerId = data.sellerDO.sellerId
             → （异步）scrape_user_profile(userId)
                   拦截 mtop.idle.web.user.page.head
                        mtop.idle.web.xyh.item.list
                        mtop.idle.web.trade.rate.list
             → AI / 关键词规则决策（我们可丢弃）
             → save_result_record（SQLite INSERT OR IGNORE）
```

### 2.3 逐项问答

#### 1. 搜索请求如何发送？

**不自己构造签名 HTTP。** 用 Playwright 打开真实搜索页，浏览器自己发搜索 POST；代码用 `page.expect_response` **等待并读取响应体**。

证据：`src/scraper.py`（`scrape_xianyu` / `_run_scrape_attempt`）、`src/services/search_pagination.py`。

#### 2. 网页接口 / MTOP / 浏览器 / 其他？

**混合：浏览器自动化 + 被动 MTOP H5 拦截。**

| 能力 | 机制 |
|------|------|
| 搜索 | 拦截 `mtop.taobao.idlemtopsearch.pc.search` |
| 详情 | 拦截 `mtop.taobao.idle.pc.detail` |
| 卖家 | 打开个人页并拦截 head / item.list / rate.list |
| 签名 | **不处理**；由浏览器会话内置 token 完成 |

#### 3. 登录态如何保存？

1. Chrome 扩展导出 goofish 标签页 cookies + env + headers 等快照；
2. Web UI 粘贴 → `POST /api/accounts` → 写入 `state/<name>.json`；
3. 爬虫启动时把 JSON 注入 Playwright `storage_state` / context。

登录态在 **文件系统**，不在 SQLite。

#### 4. Cookie / Token / Headers 如何管理？

- 增强快照：`cookies` + `_build_context_overrides`（UA/locale/viewport）+ `_build_extra_headers`；
- 无独立 token 库；MTOP 鉴权随浏览器 Cookie（含 `_m_h5_tk` 等）走；
- 多账号：`RotationPool` + 账号策略服务（我们 MVP 可先单账号）。

#### 5. 如何获取搜索结果？

1. 拦截搜索 API JSON；
2. `_parse_search_results_json` 遍历 `data.resultList[]`；
3. 从 `data.item.main.exContent`、`clickParam.args`、`targetUrl` 抽字段；
4. 翻页：点「下一页」并再次 expect 同一 API。

#### 6. 商品数据结构（列表级，解析后）

大致字段（中文 key，来自 parsers）：

```text
商品标题, 当前售价, 商品原价, “想要”人数, 商品标签,
发货地区, 卖家昵称, 商品链接, 发布时间, 商品ID
```

详情再补：图片列表、浏览量等。  
**搜索列表通常只有卖家昵称，没有可靠 sellerId。**

最终落库信封还包一层：`爬取时间 / 搜索关键字 / 商品信息 / 卖家信息 / ai_analysis`。

#### 7. 如何获取商品详情？

新开 page → `expect_response(DETAIL_API_URL_PATTERN)` → `goto(商品链接)` → 解析 `data.itemDO` + `data.sellerDO`。  
若 `FAIL_SYS_USER_VALIDATE` → `RiskControlError`。

配置常量：`src/config.py` → `DETAIL_API_URL_PATTERN`。

#### 8. 如何从商品得到卖家 ID？

**只在详情响应里：**

```text
data.sellerDO.sellerId  →  user_id
```

搜索阶段不够用。

#### 9. 商品与卖家如何关联？

- 运行时：详情解析出 `sellerId`，再去个人页拉画像；
- 个人页 URL：`https://www.goofish.com/personal?userId={sellerId}`；
- DB：**无独立 sellers 表**；卖家信息塞进 `result_items.raw_json` / `seller_nickname`；
- `SellerProfileCache` 按 sellerId TTL 缓存（默认约 1800s）。

对我们：必须把 **Seller 提升为一级实体**，不要学 Asher 把卖家埋在结果 JSON 里。

#### 10. 如何去重？

| 层 | 键 | 行为 |
|----|----|------|
| 运行时 | `get_link_unique_key(link)` = 链接第一个 `&` 之前 | 已见则跳过详情 |
| DB | `UNIQUE(result_filename, link_unique_key)` | `INSERT OR IGNORE`，不覆盖 |
| 回退 | `item:{商品ID}` 或内容 hash | 链接缺失时 |

实用身份：**商品 URL 前缀（通常含 itemId）**；`商品ID` 为辅。

#### 11. SQLite 如何保存？

默认 `data/app.sqlite3`：

| 表 | 用途 |
|----|------|
| `tasks` | cron、关键词、过滤、账号、决策模式 |
| `result_items` | 每条发现结果 + `raw_json`；status active/hidden/expired |
| `price_snapshots` | 按 run 追加的市场价格样本 |
| `result_blacklist_rules` | 标题黑名单 |
| `app_metadata` | 迁移标记 |

**结果是 append-only**：再次爬到同一商品不会更新价格/标题。价格变化走另一张 snapshot 表（服务「行情参考」，不是店铺监控）。

#### 12. 定时任务如何设计？

- APScheduler（上海时区）；
- 每个启用且有 cron 的任务 → 子进程：`python -u spider_v2.py --task-name ...`；
- 进程隔离，控制面不跟长爬虫绑死；
- `FailureGuard`：连续失败可暂停，cookie 更新可解冻。

#### 13. 真正属于「商品发现核心」的代码

| 文件 | 符号 / 内容 |
|------|-------------|
| `src/scraper.py` | `scrape_xianyu`, `_run_scrape_attempt`, `scrape_user_profile`, 风控/登录检测 |
| `src/parsers.py` | `_parse_search_results_json`, `parse_user_head_data`, `_parse_user_items_data` |
| `src/services/search_pagination.py` | `is_search_results_response`, `advance_search_page` |
| `src/config.py` | Detail/Search API pattern |
| `src/utils.py` | `get_link_unique_key`, `safe_get` |
| `src/hard_filter.py` | `apply_hard_filters` |
| `src/services/result_storage_service.py` | `load_processed_link_keys`, `save_result_record` |
| `src/services/seller_profile_cache.py` | TTL 合并加载 |
| `chrome-extension/` | 登录快照格式 |
| `spider_v2.py` | 薄入口 |
| `tests/fixtures/*.json` | 真实响应样例 |

#### 14. 可忽略的外围

- 整站 `web-ui/`
- AI 多模态分析、Prompt、任务 AI 生成
- 通知（ntfy / 企微 / Bark / TG / Webhook）
- Dashboard / WebSocket / 管理鉴权
- 结果导出 UI、黑名单 UI（思想可留，实现可后做）
- Docker/桌面启动器（部署关注点）

### 2.4 Asher：值得抽取 vs 必须丢掉

**值得重新实现（思想 + 接口契约）：**

1. 关键词 → 搜索 MTOP 列表字段映射；
2. 详情拿 `sellerDO.sellerId`；
3. 稳定商品身份（itemId / URL 前缀）；
4. UI 过滤 + 代码硬过滤双保险；
5. 登录态外置文件、可轮换账号；
6. 卖家画像 TTL 缓存（多家商品同卖家时）；
7. 长任务进程隔离。

**必须丢掉 / 不照搬：**

1. AI 推荐决策作为发现主路径；
2. 无 Seller 表的「一切塞 raw_json」；
3. 结果 `INSERT OR IGNORE` 当唯一历史模型（我们需要店铺级可更新 + 事件历史）；
4. 把卖家列表 API 仅当 enrichment，而不是监控入口。

### 2.5 Asher 设计思想（为什么这样设计）

| 问题 | 作者的选择 | 对我们的启发 |
|------|------------|--------------|
| 为何用浏览器拦截而不是直接签 MTOP？ | 规避签名/风控逆向，复用真实会话 | MVP 可 **搜索走拦截或直签二选一**；店铺列表已有成熟直签路径（见 zpl11），优先直签减负 |
| 为何搜索与「店铺监控」未拆成对等模块？ | 产品目标是关键词捡漏，不是商家研究 | **我们必须拆开**：discovery ≠ seller_monitor |
| 为何用 link 前缀当唯一键？ | 跟踪参数多变，itemId 在 URL 里稳定 | 我们应 **显式以 itemId 为 PK**，URL 仅展示 |
| 为何结果不覆盖？ | 「首次发现即告警」语义 | 发现池可 append；**店铺商品状态必须可更新 + 另存事件** |
| 为何 sellerId 来自详情？ | 列表不保证给 ID | 发现链必须走到详情（或找到列表里隐藏的 userId 字段后再优化） |

---

## 3. 项目 B：zpl11/xianyu-automation

### 3.1 项目结构（与店铺监控相关）

| 区域 | 路径 | 角色 |
|------|------|------|
| **监控核心** | `server.mjs`, `shop_monitor_direct.mjs`, `xianyu_api.mjs` | session → MTOP list → diff |
| 早期探索 | `shop_monitor.mjs`, `shop_monitor_v2.mjs` | CDP 打开个人页拦截（演进前） |
| 独立包 | `xianyu-standalone-app/server.mjs` | 与 root server 近拷贝 |
| 样例数据 | `shop_data.json`, `output.json` | 状态与原始 cardList |
| Web UI | `public/index.html` | 手动「开始监控」 |
| 较重服务 | `xianyu_monitor_service/` | cron + Playwright + SQLite |
| **可忽略** | Android/MCP 文档与 `*.py`、mitm 安装包、多数 `testCode/` | 另一条产品线 |

> 注意：`系统底层架构与运行原理.md`、`整体流程构建.md` 讲的是 **安卓平板 + uiautomator2**，**不是** PC 店铺列表监控真相。店铺监控以 README + `shop_monitor*` / `server.mjs` / `xianyu_api.mjs` 为准。

### 3.2 zpl11 核心调用链

```text
sellerId (userId)
  → CDP/已登录 Chrome：Network.getAllCookies
  → 抽出 Cookie 串 + _m_h5_tk（token = 值中 `_` 前段）
  → callMTOP('idle.web.xyh.item.list', {
        needGroupInfo: true,
        pageNumber: N,
        userId: String(sellerId),
        pageSize: 20
     }, { spm_cnt: 'a21ybx.personal.0.0' })
  → 分页直至收齐（totalCount / 20 或 nextPage）
  → 规范化 cardData → { itemId, title, price, image, url }
  → Store 以 itemId 为键
  → Diff：
        不在 store        → NEW
        在 store 且价变   → PRICE_CHANGE
        在 store 且题变   → TITLE_CHANGE
        本次 API 缺失
          且 status=active 且 checkCount>1 → SOLD_OUT / REMOVED
  → 持久化 JSON（items + changes + history）
  → （可选）taobao.idle.pc.detail 拉浏览/想要等；遇 x5sec 则浏览器刷新
```

权威实现优先级：

1. `server.mjs` → `ShopStore.fetchAndSync`
2. `shop_monitor_direct.mjs` → `getShopItems` + `Store.syncItems`（列表→差分最清晰）
3. `xianyu_api.mjs` → `createSign` / `callMTOP` / `getShopItems`

### 3.3 逐项问答

#### 1. 如何根据 sellerId 获取卖家商品？

主动调用 MTOP `idle.web.xyh.item.list`，body 带 `userId`，分页 `pageSize=20`。

#### 2. 具体接口？

| 用途 | API | Host |
|------|-----|------|
| 店铺在售列表 | `mtop.idle.web.xyh.item.list` | `https://h5api.m.goofish.com/h5/.../1.0/` |
| 商品详情/统计 | `mtop.taobao.idle.pc.detail` | 同上 |
| （外围）搜索 | `mtop.taobao.idlemtopsearch.pc.search` | 同上 |

店铺页：`https://www.goofish.com/personal?userId={sellerId}`

#### 3. MTOP 如何构造？

证据：`xianyu_api.mjs` `createSign` / `callMTOP`。

```text
APP_KEY = 34839810
token   = cookie `_m_h5_tk` 中 `_` 之前
dataStr = JSON.stringify(data)
sign    = md5(`${token}&${t}&${APP_KEY}&${dataStr}`)
POST    data=<urlencoded dataStr>
Query   jsv, appKey, t, sign, v, type=originaljson, api=mtop.{name}, ...
Header  Cookie, Origin/Referer=https://www.goofish.com/, UA
响应    可能是纯 JSON 或 mtopjsonpN(...)
```

#### 4. 哪里用 Chromium/CDP？

- `refreshSession` / `getSession`：从已登录标签页取 Cookie；
- `refreshX5sec`：导航商品页过验证；
- Docker：Chrome `--remote-debugging-port=9222` + 持久化 `chrome-data`；
- 早期 `shop_monitor*.mjs`：整页导航拦截（已非主路径）。

#### 5. 为什么需要浏览器？

1. **拿登录 Cookie + `_m_h5_tk`**（签名原料）；
2. **处理 `pc.detail` 的 x5sec / FAIL_SYS_USER_VALIDATE**；
3. **列表轮询在 Cookie 有效时不需要每次开浏览器** —— 这是关键性能/稳定性结论。

#### 6. 哪些可直接 API？

有效 Cookie 下：店铺全量在售列表（id/title/price/image/status）、搜索；偶发带有效 x5sec 时可直打 detail。

#### 7. 哪些必须浏览器？

首次/刷新登录；Cookie 收获；detail 遇验证时的挑战；以及「打开个人页滚动」的旧路径。

#### 8. 登录状态？

- Chrome user-data-dir 持久化；
- 运行时 `_session`：cookies + token；
- 未登录则监控接口 401；
- `shop_monitor_direct` 每轮可刷新 session；
- `xianyu_monitor_service` 另有 `xianyu_cookies.json`。

#### 9. x5sec 等验证？

- 检测：`ret` 含 `FAIL_SYS_USER_VALIDATE`；
- 策略：**不要伪造 x5sec**；让 Chrome 打开商品页自然过验证，再继续；
- **列表 API 作者按「无需验证」使用**（仍可能风控，需我们自己做退避）。

#### 10. 商品列表数据结构？

原始：

```text
result.data.cardList[].cardData
  id | detailParams.itemId
  title
  priceInfo.price | detailParams.soldPrice
  picInfo.url
  itemStatus
  detailUrl
result.data.totalCount / nextPage*
```

规范化存档（`shop_data.json` 思想）：

```text
itemId, title, price, url,
firstSeen, lastSeen, checkCount,
status: active | sold_out,
history: [{ timestamp, title, price }],
changes: [{ timestamp, type, message }]
```

#### 11–14. NEW / 下架 / 改价 / 改标题

| 事件 | 判定 |
|------|------|
| NEW | `items[itemId]` 不存在 → 建档；**首次全量同步时全部会是 NEW（基线）** |
| SOLD_OUT/REMOVED | 上次 active 且 `checkCount > 1`，本次 API 集合中消失 |
| PRICE_CHANGE | `existing.price !== item.price`（字符串比较） |
| TITLE_CHANGE | `existing.title !== item.title` |

`checkCount > 1` + **空列表不写盘**：防止半次失败被误判成「全店下架」。

#### 15. 历史存在哪？

| 实现 | 存储 |
|------|------|
| `server.mjs` | `data/shop_{userId}.json` |
| `shop_monitor_direct` | `shop_data.json` |
| monitor_service | SQLite + 可选 snapshot 文件 |

我们应改为 **SQLite：Item + ItemSnapshot + ItemEvent**，而不是每店一个 JSON。

#### 16. 调度？

| 路径 | 方式 |
|------|------|
| Web `server.mjs` | 无 cron，用户点「开始监控」 |
| `shop_monitor_direct` | `while` + `--interval` |
| monitor_service | node-cron，`isRunning` 防重入 |

我们需要：**合理轮询 + 随机抖动 + 错误退避 + 账号异常暂停**。

#### 17. 如何避免重复事件？

- 主键 `itemId`：已存在不再 NEW；
- 分页 `seenIds` 去重；
- 仅值变化时记 PRICE/TITLE；
- SOLD_OUT 只在状态迁移时记一次；
- 空响应不覆盖；
- 调度锁防并发双跑。  
无独立 event_id；幂等靠「状态已等于新值」。

#### 18. 真正的「店铺监控核心」

```text
Session 收获
MTOP 签名调用
idle.web.xyh.item.list 分页
cardData → 标准 Item
snapshot / diff 引擎
事件：NEW | REMOVED | PRICE_CHANGED | TITLE_CHANGED
持久化 + 历史封顶
（可选）detail + x5sec 刷新 —— MVP 可后置
```

### 3.4 zpl11：值得抽取 vs 必须丢掉

**值得重新实现：**

1. MTOP 签名与 `idle.web.xyh.item.list` 契约；
2. itemId 身份 + snapshot 差分；
3. `checkCount` / 空响应保护；
4. 浏览器仅作 auth/x5sec，列表走 HTTP；
5. 每商品 history 与全局 changes 的思想（落到 SQLite）。

**丢掉 / 后置：**

1. 五维统计批量查询 UI、CSV 导出；
2. Android/MCP 自动化文档线；
3. 早期纯 CDP 翻页方案（除非直签失败需 fallback）；
4. 手工输入店铺 ID 的交互（我们由 discovery 自动入池）。

### 3.5 zpl11 设计思想

| 问题 | 作者的选择 | 对我们的启发 |
|------|------------|--------------|
| 为何必须 snapshot？ | 平台无 changelog API | **所有「上新/下架/改价」都是差分产物** |
| 为何 itemId 而非标题？ | 标题会改 | **商品身份 = itemId；标题是可变属性** |
| 为何保留历史而不是覆盖？ | 要审计行为与导出 | **Item 当前态可更新；事件/快照追加** |
| 为何列表与详情分离？ | 列表便宜；详情易触发 x5sec | MVP 监控只依赖列表字段即可 |
| 为何 checkCount>1 才判下架？ | 首次/失败响应会「看起来像清空」 | 必须写入我们的 diff 引擎 |

---

## 4. 两项目能力链（如何接到我们的业务）

```text
┌─────────────────────────────────────────────────────────┐
│  Phase：Discovery（启发自 Asher）                         │
│  keyword → search list → detail → sellerId               │
│  产出：Item(seed) + Seller 入池动机                        │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Phase：Seller Pool（我们独有）                           │
│  去重 sellerId；记录 source_keyword / source_item        │
│  状态：watching / paused / dropped                       │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Phase：Seller Monitor（启发自 zpl11）                    │
│  get_seller_items(sellerId) → snapshot → diff            │
│  事件：NEW_ITEM / REMOVED / PRICE / TITLE                │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Phase：Candidates（我们独有）                            │
│  NEW_ITEM 且「不像原始关键词目标商品」→ Candidate         │
│  聚合：seller_count / appearance_count / score           │
│  不做自动上架；只供人工实验                                │
└─────────────────────────────────────────────────────────┘
```

### 可复用的思想清单

1. **发现与监控分离**（Asher 缺后半段、zpl11 缺前半段 —— 正好证明应拆模块）。
2. **sellerId 一级实体**（两项目都弱；我们必须强）。
3. **itemId 身份 + 属性可变**。
4. **历史追加 / 当前态更新** 双轨。
5. **浏览器最小化**：auth 用浏览器，列表尽量 HTTP。
6. **失败不能当全店下架**。
7. **发现 ≠ 有价值**（Asher 的 AI 层证明「判定」应后置；我们用 Candidate status 人工验证）。

### 明确忽略

- Asher：Web UI、AI、多通道通知、任务 AI 生成。
- zpl11：五维统计产品化、安卓 Agent、Chrome 插件旁路（除非作为 Cookie 导出备选）。
- 两边的「完整可部署产品壳」。

---

## 5. 关键 MTOP / 页面契约速查

| 步骤 | API / URL | 推荐获取方式（我们） |
|------|-----------|----------------------|
| 关键词搜索 | `mtop.taobao.idlemtopsearch.pc.search` | 优先评估直签；不行则 Playwright 拦截（Asher） |
| 商品详情 | `mtop.taobao.idle.pc.detail` | 发现阶段取 sellerId；注意 x5sec |
| 卖家在售 | `mtop.idle.web.xyh.item.list` | **HTTP + 签名（zpl11）**，MVP 主路径 |
| 卖家主页 | `/personal?userId=` | 人类核对 / fallback |
| 登录 | Cookie + `_m_h5_tk` | 外置 state；CDP 或扩展导出 |

APP_KEY（zpl11）：`34839810`（实现时以实测为准，可能变更）。

---

## 6. 对我们系统的直接设计约束（预告 Phase 2）

1. **模块边界硬拆**：`discovery` / `sellers` / `items` / `candidates` / `auth` / `scheduler` / `storage`。
2. **MVP 数据面**：SQLite；实体至少 Seller、Item、ItemSnapshot（或 ItemEvent）、SellerPool 入池记录、CandidateProduct。
3. **MVP 不做**：自动上架、自动购买、自动发货、AI 选品、复杂 GUI。
4. **CLI 可测**：`search(keyword)`、`get_seller_items(seller_id)` 独立可跑。
5. **频率**：慢、抖、退避、账号异常停 —— 优先长期存活。
6. **原仓库只读**：正式代码写在 `xianyu-radar/` 根下自有包，不改 `_research/`。

---

## 7. Phase 1 完成标准核对

| 交付 | 状态 |
|------|------|
| Asher 核心调用链 + 文件/函数/请求/结构 | ✅ 本文 §2 |
| zpl11 核心调用链 + 同上 | ✅ 本文 §3 |
| 设计思想（不仅调用关系） | ✅ §2.5 / §3.5 / §4 |
| 可复用 vs 可忽略 | ✅ |
| 两项目能力链 | ✅ §4 |
| **未**开始正式系统大规模编码 | ✅ |

---

## 8. 下一阶段

进入 **Phase 2：Architecture Design**，产出 `SYSTEM_DESIGN.md`：

- 自有架构与模块职责；
- 数据模型与数据流；
- 调度 / 状态 / 错误处理；
- MVP 边界；
- 哪些启发自 A / B，哪些是重新设计。

仍不进入大规模实现。

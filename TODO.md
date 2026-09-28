# 待解决问题清单

更新于 2026-09-28。已定位当前代码的触发位置，并按“已确认”和“待在线验证”区分原因。处理时保留失败记录和诊断信息，不把不完整的数据当作成功结果。

## 1. 发现商家：商家信息获取不稳定，容易触发限流

### 报错和数据丢失位置

1. `src/xianyu_radar/modules/discovery/keyword_search.py:17-45`：`search()` 默认只请求 `pageNumber=1`、`rowsPerPage=30`，调用方也没有翻页循环。因此当前“发现商家”最多覆盖搜索结果第一页，并不具备“所有搜索结果商家”的覆盖能力。
2. `src/xianyu_radar/modules/discovery/item_parser.py:38-49`：搜索结果只接受 `sellerId` / `seller_id` 两个字段中的纯数字值。`item_parser.py:110-126` 的图片路径兜底还要求候选 ID 唯一且无冲突；不满足这些严格条件时会保留 `seller_id=None`。`item_parser.py:130-138` 的详情兜底也只读取 `sellerDO.sellerId` / `userId` 且要求纯数字。平台字段缺失、改名、嵌套位置变化或非数字引用都会导致商家无法识别。
3. `src/xianyu_radar/modules/discovery/service.py:103-119`：搜索后会对最多 30 条缺少卖家 ID 的商品逐条请求详情。请求之间没有间隔、抖动或退避，也不复用 HTTP client；一次发现可能在很短时间内发出“1 次搜索 + 多次详情”请求，容易触发 `RGV587` 或 `FAIL_SYS_USER_VALIDATE/x5sec`。
4. `src/xianyu_radar/modules/discovery/service.py:111-117`：详情补全遇到人机验证时，只要本批已有任意商品识别出卖家，就会停止后续补全并继续保存部分结果；随后 `service.py:135-153` 跳过所有仍无卖家 ID 的商品，却把发现记录写成 `status='ok'`。这会把“受验证中断的部分成功”展示成成功，造成结果忽多忽少的观感。
5. `src/xianyu_radar/modules/discovery/service.py:58-67`：普通 `MtopError` 和未预期异常只写日志并继续，最终同样表现为“未识别卖家”，接口结果中没有逐条失败原因。
6. `src/xianyu_radar/infrastructure/goofish/mtop.py:104-112` 抛出 MTOP 错误；`src/xianyu_radar/entrypoints/api/routes/discover.py:35-51` 将 `RGV587/挤爆/稍后重试` 映射为 HTTP 429，将 `FAIL_SYS_USER_VALIDATE/x5sec` 映射为 HTTP 403。这是界面上限流和人机验证报错的直接来源。
7. `src/xianyu_radar/infrastructure/storage/schema.sql:89-97`：`discovery_runs` 只保存状态、商品数和商家数，没有保存 `error_kind`、未识别数、补全数、验证中断位置或页数。失败后无法仅靠数据库区分限流、验证、登录态和解析问题。该表的 `seller_count` 实际写入的是本次“新增商家数”（`service.py:139-152`），但 Web 历史表标题显示为“商家数”，重复发现已有商家时也容易被误解为没有获取到商家。

### 可能原因判断

- **已确认：搜索覆盖不完整。** 代码只读取第一页 30 条，后续搜索页中的商家一定不会进入商家池。
- **已确认：详情补全是突发连续请求。** 当前无请求间隔和退避；缺少卖家 ID 的结果越多，同一次发现产生的连续详情请求越多。
- **已确认：部分成功会被记为成功。** 人机验证中断后，已识别结果会入池，剩余结果被跳过，发现记录仍为 `ok`。
- **较可能：搜索响应的卖家字段不稳定或存在多种结构。** 当前解析器刻意只接受少量可验证的数字字段；这是防止错误商家入池的保护，也会降低覆盖率。需要保存脱敏响应样本才能确认还缺哪些字段分支。
- **较可能：平台风控综合判断了 Cookie、访问频率、请求指纹或近期请求历史。** 当前固定 User-Agent 和请求头、每次请求新建连接，且详情请求密集；哪个因素主导需要低频对照实验，不能只凭 429/403 确定。
- **现有数据限制：** 本地共有 8 次发现记录，其中 5 次 `failed`、3 次 `ok`；由于表中未保存错误类型和未识别数，现有数据库无法反推 5 次失败分别属于限流、人机验证还是其他 MTOP 错误。

### 待处理

- [ ] 增加搜索分页及停止条件，记录实际请求页数、原始结果数、去重商品数和唯一商家数。
- [ ] 保存脱敏的搜索与详情解析诊断，逐项补齐已验证的卖家 ID 字段来源；无法确认的候选仍不得入池。
- [ ] 为详情补全增加请求间隔、抖动、分类退避和可恢复进度；遇到 429 或人机验证后停止继续请求。
- [ ] 将完整成功、部分成功、限流、需要验证和解析失败分别落库；历史列表区分“识别商家数”和“新增商家数”。
- [ ] 验收：在约定关键词和页数范围内，所有搜索结果都有处理结论；已识别商家稳定入池，未入池商品有可查原因；风控中断不会被记录为完整成功。

## 2. 扫描商家：频繁出现“分页不完整 · 1 页 · 预期 0”

### 报错位置和触发链路

1. `src/xianyu_radar/modules/scan/fetcher.py:52-61`：第一页响应的 `data.totalCount` 被直接转换并保存为 `expected_count`；值为 `0` 时也被当成可信总数。
2. `src/xianyu_radar/modules/scan/fetcher.py:63-83`：同一页的 `cardList` 被正常解析并加入 `all_items`。只要解析出至少 1 条商品，就满足 `len(all_items) > total_count`，立即以 `finish_reason='more_than_total'`、`complete=False` 返回。
3. `src/xianyu_radar/modules/scan/fetcher.py:88-104`：`nextPage` 和短页结束信号的处理位于上述返回之后，因此“预期 0、实际有商品”时根本不会执行翻页判断。这解释了为什么结果固定显示“1 页”。
4. `src/xianyu_radar/modules/scan/service.py:249-252`：不完整目录被记录为 `status='failed'`、`error_kind='incomplete'`；`service.py:165-193` 保存已读数、预期数、页数和结束原因，但不更新商品当前态，也不产生事件或候选。
5. `web/app.js:393-400`：扫描历史将上述字段组合为“分页不完整 · 1 页 · 预期 0 · more_than_total”。界面文字是后端诊断结果的直接展示，不是前端自行推断。

### 原因判断

- **高置信根因：当前实现错误地把不可用的 `totalCount=0` 当作真实总数。** 仓库研究代码 `_research/xianyu-automation/xianyu-standalone-app/server.mjs:209-210` 已明确记录该接口的 `totalCount` 总是 0，应依赖 `nextPage` 和页面数据判断结束；当前 Python 实现与这个已知接口行为冲突。
- **本地数据与该根因吻合：** 2026-09-28 有 13 次失败，涉及 11 个商家，全部为 `expected_count=0`、`page_count=1`、`finish_reason='more_than_total'`，实际读取 2–20 条；其中 9 次恰好读满第一页 20 条。这更像第一页面正常返回后被本地质量门禁提前中止，而非真的只存在一页或第二页请求失败。
- **这些记录不是商品卡片解析失败。** 如果原始卡片无法完整解析，`fetcher.py:67-68` 会得到 `unparsed_cards`；现有 13 次记录均为 `more_than_total`，说明第一页 `cardList` 已完整解析。
- **这些记录也不是直接的 MTOP 限流报错。** 限流或人机验证会由 `call_mtop()` 抛出 `MtopError`，在 `service.py:235-247` 记录为 `rate_limit` 或 `network`；本批记录已经取得成功响应并进入目录完整性判断。不过，平台是否因账号、接口版本或灰度策略把总数字段置 0，仍需保存脱敏原始响应确认。
- **保护逻辑本身有效。** 当前失败没有污染已保存商品、事件或候选；问题在完整性判断依赖了错误的总数字段，而不是应该删除质量门禁。

### 待处理

- [ ] 增加回归用例：`totalCount=0`、第一页有 20 条且 `nextPage` 指向下一页时，应继续翻页；短页或明确结束后才完成目录。
- [ ] 保存脱敏的每页诊断，至少包括 `totalCount` 的原始类型和值、`cardList` 数量、解析数量、`nextPage/nextPageNum`、请求页码和去重后累计数。
- [ ] 将 `totalCount=0 且 cardList 非空` 视为“总数不可用”，改用明确的下一页/结束信号；总数为正数时继续执行一致性校验。
- [ ] 明确无可靠总数时的结束、空页、重复页、最大页数和复扫规则，同时保留不完整扫描不得更新商品当前态、事件或候选的保护。
- [ ] 验收：正常有商品的店铺可以完成多页扫描；总数不可用时不再在第一页误报 `more_than_total`；真正的分页缺失仍有明确诊断且不写入业务变化。

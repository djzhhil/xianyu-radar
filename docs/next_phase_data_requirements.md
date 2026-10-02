# 下一阶段数据需求与自动发货系统探查记录

日期：2026-10-02。字段名是目标映射示例，不要求现有系统改表。

## 1. 最先需要的数据

| 数据 | 建议起始规模 | 必要内容 | 用途 |
| --- | --- | --- | --- |
| 重点商家 | 3–5 家，可更少 | 店铺链接或 seller ID、为什么值得参考 | 验收主动入池和目录监控 |
| 自有商品 | 10–20 条样本，确认格式后导全量 | 稳定商品 ID、名称；实际可取得的状态、规格和链接 | 对照哪些已售，避免重复补货 |
| 商品匹配示例 | 约 5 组 | 商家商品与自己的商品是否相同、原因 | 明确版本、套餐和异名匹配规则 |
| 业务分类说明 | 简短文字即可 | FDE 指代的主题、常见版本差异、明显不相关类别 | 相关性筛选和人工复核 |

最先完成商品对照无需全量订单。订单样本用于提前验证成交数据是否能用，随后再决定实际导入范围。

## 2. 自有商品的目标字段

| 目标字段 | 优先级 | 说明 |
| --- | --- | --- |
| `source_system`、`source_product_id` | 必要 | 联合形成稳定身份；一份名称不能充当稳定 ID |
| `title` | 必要 | 自己实际售卖的商品名 |
| `platform_item_id`、`url` | 有则提供 | 区分发货配置 ID 和平台商品 ID，保留对应关系 |
| `variant`、`version`、`bundle` | 有则提供 | 版本、年份、语言、单品/套餐；可先人工填写 |
| `listing_status` | 有则提供 | 是否真实在售；配置启用、发货启用不一定等于在售 |
| `price`、`currency` | 有则提供 | 标价和币种，标价不是实付金额 |
| `created_at`、`updated_at` | 有则提供 | 时间格式和时区需说明；没有时不推断上架日期 |

若只有关键词触发规则和发货卡片，没有商品表，先导出规则 ID、匹配条件以及可用的平台商品映射，再人工建立商品清单。卡片数量、规则数量都不能直接当作售卖商品数量。

## 3. 订单样本与成交口径

建议少量样本覆盖付款、发货、取消、退款及重复发货等现有状态；没有某种记录时标明未验证即可，不要求造数据。格式确认后，可用最近 30 天的数据做首轮对账，再决定是否扩展到 90 天。

| 目标字段 | 作用与缺失处理 |
| --- | --- |
| `source_order_id` | 稳定订单身份，重试和重复导入不重复统计；只有消息 ID 时先确认是否对应订单 |
| `source_product_id` / `platform_item_id` | 与商品关联；一单多品时需订单明细或明确分配口径 |
| `ordered_at`、`paid_at` | 区分创建与付款，说明时区和时间单位 |
| `paid_amount`、`currency`、`quantity` | 实付金额、币种和数量；缺失金额时只统计有证据的订单数 |
| `order_status`、`payment_status` | 保留原始值，映射后再认定有效成交 |
| `refund_status`、`refund_amount` | 区分退款申请与成功、部分与全额退款；未知时不声称退款已扣除 |
| `delivery_status`、`delivered_at` | 用于发货对账，发货失败不自动等于订单取消 |
| `updated_at` | 后续订单状态更新依据；缺失时采用导入批次并保留来源 |

只有发货日志时，只能先分析发货活动，不能把一条日志认定为一笔付款成交。补发、重试、赠送、测试、取消和退款如何识别，需要根据系统实际状态和业务解释确认。

## 4. 人工补充的信息

- 哪些现有商品你确认卖得好，观察时间和依据是什么。
- 一份资料通常怎样取得、整理需要多久，哪些资料目前无法获得。
- 哪些商家值得优先观察，哪些商品类型你不准备售卖。
- 商品图片、文案、图集、版本信息中，下一阶段最常需要查看的内容。

投入、退款、咨询等缺失信息保持未知，不当作零。实际交付文件及下载口令不是这次对照所需数据。

## 5. 交付格式和核对方法

优先 CSV（UTF-8，保留带引号的换行文本）或 JSON，商品与订单分别提供。可以附字段名、少量脱敏样例及状态说明，格式确认后再导出较大范围。ID 按字符串保留，金额说明元/分，时间说明时区，空值与零分开。

样本无需买家姓名、联系方式、地址、聊天原文、登录 Cookie、账号密码、API 密钥、卡密或资料访问口令。跨文件关联 ID 如需脱敏，应一致替换，保持商品和订单之间的对应关系。

核对时先检查稳定 ID 是否唯一、商品关联覆盖率、时间范围和状态分布，再挑几笔已知订单人工对账。不能关联、重复和状态不明确的行保留诊断，不静默丢弃。

## 6. 自动发货系统初步探查

授权范围：`10.0.0.8` 上现有业务系统的只读初步探查。2026-10-02 已由子代理执行连接检查，未进入业务系统。

| 检查项 | 结果 |
| --- | --- |
| SSH 网络连接 | `10.0.0.8:22` 可达，严格主机校验通过 |
| 认证 | 首次默认身份失败；用户确认 `root` 及密钥命名后，显式指定已有密钥登录成功 |
| 部署 | `/opt/xianyu-helper/current` 指向 `releases/prod-20260929-r2`；应用容器与 PostgreSQL 容器健康检查均为 healthy |
| 数据库 | PostgreSQL 17；已读取有限表名和商品、订单字段元信息 |
| 查询保护 | `default_transaction_read_only=on`、`statement_timeout=3000`、`lock_timeout=1000` |
| 对生产系统的操作 | 连接及有限结构读取；未修改文件、配置或业务数据，未启停服务、执行发货、安装程序或扫描端口 |

首次错误 `Permission denied (publickey,password)` 表示当前默认身份无法认证，已通过用户指定的身份配置解决，保留严格主机校验。

### 已确认的业务表和字段

数据库有独立商品表 `item_info` 和订单表 `orders`，另有 `cards`、`delivery_templates`、`order_reconciliations`、`order_refresh_jobs`。本次未读取实际业务记录或状态分布。

| 表 | 已确认的相关字段 | 导入注意点 |
| --- | --- | --- |
| `item_info` | `cookie_id,item_id,item_title,item_description,item_category,item_price,item_detail,is_multi_spec,multi_quantity_delivery,created_at,updated_at,deleted_at` | `item_price` 是文本；是否在售不能只凭存在商品行或 `deleted_at` 判断。初次导出不需要描述和 `item_detail` |
| `orders` | `order_id,item_id,cookie_id,spec_name,spec_value,quantity,amount,order_status,system_shipped,created_at,updated_at,paid_at,shipped_at,completed_at,deleted_at` | 数量、金额和付款/发货/完成时间为文本；`created_at/updated_at` 为无时区 timestamp，需确认业务时区 |

商品关联建议以 `(cookie_id,item_id)` 为起点，`cookie_id` 作为不透明账号引用，可一致脱敏；它不是需要导出的 Cookie 凭据。商品身份与订单唯一约束仍需正式导入前核对，不能只看字段名假定主键。软删除记录和多规格商品必须有明确处理规则。

`amount` 是否实付、`paid_at` 是否完整、订单状态是否同步到退款最终结果，都未通过记录核对。`system_shipped` 也不能单独证明付款成功。表中存在买家和收货信息相关字段，导出白名单应排除它们。

### 推荐第一份数据包

1. 商品：`cookie_id,item_id,item_title,item_category,item_price,is_multi_spec,created_at,updated_at,deleted_at`，先给 10–20 条样本，再确认全量范围。
2. 订单：`order_id,cookie_id,item_id,spec_name,spec_value,quantity,amount,order_status,system_shipped,created_at,updated_at,paid_at,shipped_at,completed_at,deleted_at`，先给少量不同状态样本，不直接拉全库。
3. 原始状态含义、金额单位、业务时区，以及测试单、补发、退款如何识别的说明。

以上是实际字段白名单，不要求生产系统新增字段。没有读取商品或订单正文，故仍需脱敏样本验证内容格式。应用容器内为编译后二进制，本次未取得源代码中的状态映射；已有后台 CSV/API 导出入口也未验证，不能声称已有可直接使用的接口。优先请用户通过已有后台提供样本；若无导出能力，再制定限定字段和范围的只读提取方案。本次探查不代表已授权新增导出程序或持续查询生产数据。

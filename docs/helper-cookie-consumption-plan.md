# Reader 改用 Helper 管理 Cookie 的实施计划

日期：2026-10-03。状态：Reader 已按固定契约完成实现和离线验收；具体交付、验证及恢复能力限制见 [验收记录](helper-cookie-implementation.md)。生产部署与真实联调未执行。

Reader 指本仓库 `xianyu-radar`，检查基线为 `7243743`。Helper 生产基线为 `cb559f8`，配套契约位于 `/root/projects/xianyu-helper-project/worktrees/production/docs/cookie-exchange-integration-plan.md`。实施时重新核对两项目当前代码，以 Helper 文档为第一版接口契约依据。

## 1. 核心目标

将闲鱼 Cookie 的持久化、登录、续期和权威状态全部交给 Helper。Reader 保留自己的搜索、商家发现、商品详情、扫描及结果数据库；只在一次操作期间持有必要的临时 Cookie 会话。

Reader 不再保存闲鱼 Cookie JSON、不接受网页粘贴 Cookie、不自动续期或扫码登录、不在 Helper 故障时偷偷退回旧本地 Cookie。暂存 Helper 管理会话和本次闲鱼请求 Jar 只允许在后端内存，不进入浏览器、localStorage、SQLite、state JSON 或诊断文件。

Reader 改动范围可以较大，但应沿 API/CLI 入口、auth 公共入口、Helper 客户端、MTOP 会话执行链修改，不让 discovery/scan/products 分别实现一套 Cookie 管理。不把项目改为 Helper 的闲鱼请求代理；闲鱼业务请求仍由 Reader 发出。

## 2. 当前问题和应修改的位置

| 当前位置 | 当前行为 | 修改建议 |
| --- | --- | --- |
| `infrastructure/goofish/session.py` | 从 state JSON 加载，Cookie 数组压成字符串，签名 Token 只提取一次 | 改为完整快照的临时 Session，按 URL/页面生成 Cookie 和 Token |
| `infrastructure/goofish/mtop.py` | 使用固定 Cookie/token，未持久化响应 Set-Cookie，TOKEN 与 SESSION 粗略合并为 AuthError | 接收每跳 Cookie，先提交更新再判断业务结果，有限 Token 重试，区分错误 |
| `modules/auth/service.py` | 导入、保存本地登录态，检查和解除暂停 | 改为 Helper 连接状态、获取快照、检查账号、重新加载与暂停控制 |
| `entrypoints/api/deps.py`、`entrypoints/cli.py` | require_session / load_session 读取本地文件 | 共用 Helper Session Provider，每次操作/扫描轮次获取最新状态 |
| `entrypoints/api/routes/auth.py` | 接受上传/粘贴 Cookie | 移除在线写入能力，返回明确的迁移提示，不继续保存 |
| `entrypoints/api/routes/status.py` | 查看本地 state 文件、Cookie 数量和 token_prefix | 返回 Helper 来源、账号、连接/暂停/同步状态，不返回 Token 前缀和秘密 |
| `modules/scan/runner.py` | 长期循环复用启动时的 Session | 每轮重新获取；冲突、认证失败和回写不确定时停止当前操作 |
| `modules/discovery/service.py`、`enrichment.py`、`modules/scan/fetcher.py`、`modules/products/service.py` | 多条调用链共享旧 Session 或临时 HTTPClient | 统一经过新 MTOP 客户端，不绕过 Cookie 接收和提交 |
| `web/app.js`、`web/common.js` 及实际登录态视图 | 本地 Cookie 输入、检查提示 | 改为 Helper 来源与账号状态；登录/续期指导指向 Helper |
| `config.py`、`docs/session_format.md`、README | 本地 Cookie 配置和说明 | 更新为 Helper 配置及迁移说明，不把旧说明留作默认可用入口 |

实际 UI 文件位置以实施时 `rg` 检查为准。保留选品、候选、事件和商家数据，不因登录态迁移删除业务数据库。

## 3. 共用模块和配置

建议新增：

- `infrastructure/helper/client.py`：Helper 管理认证、两个交换接口、超时及错误转换。
- `infrastructure/helper/session_provider.py`：按账号取得临时 Session，操作生命周期和串行控制。
- `infrastructure/goofish/cookie_jar.py`：完整快照作用域、签名 Cookie、逐跳 Set-Cookie 处理；与 Helper 用同组协议夹具验证。

可以按现有代码规模合并文件，但必须只有一个公共获取入口和一个回写入口。不要让业务模块互相导入内部服务。网络请求使用现有 httpx，不为了头部处理引入重型依赖。

部署配置建议：`RADAR_HELPER_BASE_URL`、`RADAR_HELPER_USERNAME`、`RADAR_HELPER_PASSWORD`、`RADAR_HELPER_ACCOUNT_ID`。这四项是新建议配置，不是当前已支持选项。账号由服务端配置指定，不让浏览器任意传账号 ID 绕过边界。

Helper 会话客户端只连接配置的 Helper 地址，调用现有 `POST /api/v1/session/login`，正文为 `username`、`password`；从响应 Set-Cookie 建立管理会话。无效密码不持续重试，401 允许一次受控重新认证，403/404 明确停止。

闲鱼 HTTP 客户端完全独立，不能携带 Helper 登录 Cookie。Helper 的账户密码、认证会话和闲鱼 Cookie 不进入响应、日志或命令行参数。现有 `RADAR_HTTP_PROXY` / `RADAR_HTTPS_PROXY` 保留给闲鱼出站链，不能默认把 Helper 认证流量也发给该代理；Helper 如需代理应另行明确。

## 4. 与 Helper 固定契约

### 获取

`GET /api/v1/integrations/accounts/{account_id}/cookie-snapshot`

成功字段：`account_id`、`credential_version`、`snapshot_complete=true`、`cookies`。Cookie 使用 `name`、`value`、`domain`、`path`，以及可选的 `expires`、`httpOnly`、`secure`、`sameSite`、`partitionKey`；字段默认和作用域语义以 Helper 计划为准。

只接受完整快照。409 `cookie_snapshot_unavailable` 提示在 Helper 登录，不把残缺响应转换成本地扁平 Cookie。缺少 `_m_h5_tk` 不直接等同 Session 被平台撤销；它属于签名 Token 缺失，交给有限 Token 恢复流程。

版本只透传，不从 last_refresh_at 推测、不自己计算。

### 回写

`POST /api/v1/integrations/accounts/{account_id}/cookie-updates`

```json
{
  "credential_version": "v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "responses": [
    {
      "response_url": "https://h5api.m.goofish.com/h5/example/1.0/",
      "received_at": "2026-10-03T08:00:00.000Z",
      "set_cookies": ["example=value; Domain=.goofish.com; Path=/; Max-Age=3600; Secure"]
    }
  ]
}
```

按原响应顺序收集批次。URL 使用实际请求地址并去除 query/fragment，不用最后一跳 URL 替代中间跳；`received_at` 在收到响应头时记录；httpx 使用保留多条字段的方法提取 Set-Cookie，不对逗号进行拆分。失败正文和失败 HTTP 状态也可能有 Cookie 更新，先接收与提交后再分类。

Helper 第一版只接受 HTTPS 的 `h5api.m.goofish.com`、`www.goofish.com`、`passport.goofish.com`、`seller.goofish.com`，顶层分区站点固定 `https://goofish.com`。外域重定向不携带原站 Cookie，也不能提交为原账号更新。优先关闭自动重定向并显式逐跳处理；最大 5 跳，循环或不合法目标停止。Helper URL 本身不接受用户输入的闲鱼响应地址转发。

遵循 Helper 的体积、批次和时间限制：256 KiB、最多 32 批、每批 128 条、每条 8 KiB，接收时间相对 Helper 不超过未来 30 秒或过去 10 分钟。超过时停止并提示，不拆分旧版本请求强行重放。

响应字段：`account_id`、`changed`、新的 `credential_version`、`runtime_sync_status`。同步状态为 `synced`、`not_running`、`not_needed` 或 `failed`。`failed` 仍表示 Cookie 已提交，不重发旧更新；Reader 可显示非敏感提醒。

两个接口只处理 Cookie，不把它们当作 Helper 保证本次闲鱼请求成功或代 Reader 解决风控的接口。

部署前在 Helper 确认目标账号满足既有后台续期的启用条件。Reader 获取或回写不能自动启用账号，拿到停用账号的快照不表示该账号会持续续期。

## 5. 一次业务操作的执行流程

```text
进入 API / CLI 操作
→ 按配置账号取得 Reader 内部操作锁
→ 从 Helper 获取最新完整快照及版本
→ 创建短生命周期闲鱼 Cookie 会话
→ 按文档 URL 筛选非 HttpOnly Cookie，取首个 _m_h5_tk 生成签名
→ 按实际请求 URL 筛选请求 Cookie
→ 执行闲鱼请求并逐跳接收 Cookie
→ 有更新则向 Helper 提交；采用成功返回的新版本
→ 判断业务结果，必要时执行一次受控 Token 恢复
→ 后续分页/详情请求继续上述请求与提交过程
→ 操作结束销毁临时会话并释放操作锁
```

本地按账号串行控制用于避免 Reader 自己的多个操作持有同一个旧版本。操作锁覆盖一个有界操作，不能无限持有后台循环，也不能持锁等用户输入。扫描循环每轮重新获取，轮次之间释放锁；其他 Reader 进程仍可能冲突，依靠 Helper 409 处理，不声称分布式锁。

新 Jar 必须保留同名 Cookie 的域、路径、HttpOnly、有效期和分区属性，发送时长路径在前。签名取页面可见首个匹配 Token，不能先压成 map 再取最后一个。cookie header 与签名 token 每次请求动态计算。

Reader 可以在内存先吸收响应更新供当前解析/重定向使用；所有更新提交确认前，不启动新的独立业务请求或分页。提交失败后销毁本地会话，不继续使用未确认的凭证。

## 6. 冲突、故障和恢复规则

| 情况 | Reader 行为 |
| --- | --- |
| 获取时 Helper 不可达 | 停止在线操作，返回依赖故障；本地查看既有商品/候选仍可用，不退回旧 Cookie |
| Helper 401 | 一次重新认证；仍失败则提示 Helper 登录配置，不误报闲鱼 Session 过期 |
| Helper 403/404 | 停止，提示账号归属或配置错误 |
| 无完整快照 | 提示在 Helper 重新登录，不把旧 JSON 当备用 |
| 回写 409 | 丢弃本地会话和旧响应增量，重新获取用于下一次有界操作；不能把旧增量贴上新版本再发 |
| 回写超时、连接中断或 5xx | 保存结果可能未知，停止当前操作并重新获取状态；禁止盲目重发；保留已确认业务数据但不宣称全量完成 |
| 同步状态 failed | Cookie 已提交，采用返回版本；非敏感提示 Helper 同步异常，不重复回写 |
| TOKEN_EMPTY / TOKEN_EXPIRED / TOKEN_EXOIRED | 接收并提交轮换 Cookie 后，只允许有限 Token 恢复与原只读请求重试，不直接设置 Session 失效 |
| SESSION_EXPIRED / SID_INVALID / NEED_LOGIN 等 | 暂停本次在线工作，提示在 Helper 恢复；重新获取本身不会触发续期 |
| FAIL_SYS_USER_VALIDATE | 停止后续请求，记录验证状态；不得用刷新 Cookie 循环代替验证 |
| 限制/限流响应 | 停止当前批次，保留进度，不立即多次换 Cookie 重试 |

第一版不新增 Helper 的第三个恢复接口。缺失签名 Token 时，Reader 可参考 Helper 现有 MTOP Token 交换流程，在临时会话中有限获取签名凭证；这不保存或定期续期账号。若不能在同一已授权会话内恢复，明确停止，不在 Reader 增加密码/扫码/静默登录兜底。具体 Token 请求参数和页面上下文先以现有 Helper 协议代码及离线夹具核对，不照搬到搜索接口的所有错误上。

只读业务自动重试最多一次，回写与 Token 恢复各有独立有限边界，不能嵌套成无界请求。业务 ret、HTTP 状态和依赖错误分别诊断，不能全部转成 AuthError。诊断不保存 Set-Cookie 值、签名、Token 前缀、原始 Cookie 或 Helper 密码。

全量搜索/扫描遭冲突或凭证异常后，不重复最后一项有副作用操作。当前 Reader 主要只读，也需通过已有运行进度避免重复入池和重复事件。当前计划不新增定期扫描；Web 启动仍不能自动启动 `radar run`。

## 7. 本地管理和界面迁移

1. 移除在线操作对 `data/state/default.json` 和 `--state` 的依赖。旧参数显式给出迁移错误，不能忽略后继续读取旧 Cookie。
2. 本地解析器可以为离线 fixture 保留，但不再是生产获取来源。旧 Cookie 文件不自动上传 Helper，不自动删除，文档指导用户确认后自行清理；代码不再读取。
3. `/api/auth/session` 不再保存用户提交 Cookie；明确返回已迁移提示，例如 410 和 `cookie_management_moved_to_helper`。现有 UI 先删除提交入口，防止不断请求废弃端点。
4. 登录态页显示来源 Helper、目标账号、连接状态、上次获取/提交时间、暂停原因及“重新检查”。不显示 token_prefix，不提供 Cookie 下载或浏览器复制。
5. 本地“解除暂停”不等于 Cookie 恢复。重新获取并验证后再恢复相应操作；仅获取快照不能证明闲鱼在线可用。
6. 更新 CLI 帮助、status、README、`docs/session_format.md` 和代码地图，使所有在线命令都指向同一 provider。原有业务数据库和诊断进度保持。

## 8. 实施与验证

从 main 创建一个 `codex/<topic>` 分支，按 AGENTS 保留已有改动，完成检查后提交并合并。先等待 Helper 契约实现并验证，Reader 可以提前用固定契约 mock 开发，不用真实 Cookie 联调。

建议在同一任务内完成：公共 Helper 客户端与 Jar → 所有 API/CLI 获取入口 → MTOP 响应提交和错误分类 → 扫描轮次生命周期 → 登录态界面与旧入口迁移 → 验证。无需单独建立跨业务的服务注册框架。

离线测试至少覆盖：

- 获取完整快照、缺字段、无快照、401 一次重登录、403/404、不可达和客户端秘密隔离。
- 同名 Token 的顺序、域/路径、过期/删除、HttpOnly 签名排除、Secure、分区以及稳定签名输入。
- 多条 Set-Cookie、Expires 含逗号、失败响应头、正文解析失败、重定向逐跳作用域和 Max-Age 原时间。
- 回写版本推进、无变化、409、超时结果未知、同步 failed 不重发、不同业务调用共享唯一执行入口。
- Token 过期最多一次业务重试，真正 Session/验证/限流停止后续分页和详情。
- 多线程操作串行、循环每轮重取、取消释放锁、不再从本地文件加载、Web 启动不启动扫描。
- 原有搜索解析、商家识别、目录完整性、事件去重、候选与恢复进度回归。

使用本仓库既有 pytest 环境执行相关测试并完成全量离线测试，检查 UI JavaScript 语法及实际工作台迁移。HTTP mock 验证两个接口的路径和字段与 Helper 文档一致。凭证只用明确假值，失败断言也不能打印秘密。

验收结论必须明确：Helper 是唯一持久化来源；Reader 没有生产本地 Cookie fallback；所有在线入口都有响应增量提交；回写不确定会停止工作；两种 Cookie 不串用；风控没有被掩盖成“换 Cookie 即可”。上线前单独确定 Helper 地址、有效归属账号和网络可达性，部署不自动包含在代码实施授权里。

## 9. Reader 实施提示词

> 请在 xianyu-radar 项目实施 `docs/helper-cookie-consumption-plan.md`，并核对配套 Helper 的 `docs/cookie-exchange-integration-plan.md`，不得自行改变两接口契约。按 AGENTS 从 main 创建独立分支。将所有在线 API/CLI 的 Cookie 来源改为 Helper，Helper 管理登录、持久化和既有续期；Reader 只保留操作期间的临时完整 Jar。统一 Helper 会话客户端、Session Provider 和 MTOP 响应回写，处理作用域、签名 Token、多跳 Set-Cookie、版本冲突及提交不确定状态。移除在线本地 Cookie 导入/保存及 fallback，更新登录态 UI、CLI 和文档，但不删除旧用户文件或业务数据库。不在 Reader 新增账号登录、定时续期或验证码自动化，不因 Web 启动增加定时扫描。Helper 管理会话与闲鱼会话完全隔离，秘密不进日志或浏览器。先用 mock 验证契约，完成权限、错误分类、并发、进度恢复和原有业务回归后按仓库规范提交合并。不要部署生产。最终说明修改、测试和未实现的恢复能力。

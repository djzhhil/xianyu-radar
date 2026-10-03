# Helper Cookie 接入验收记录

日期：2026-10-03。Reader 实施分支：`codex/helper-cookie-consumption`。实施起点为 Reader `694a8db`；重新核对的 Helper production 为 `9c2f4a8`，当时其交换接口尚未注册，契约依据为配套文档。后续对 Helper `bb404bc` 实现的核对及发布检查见 [发布检查记录](helper-cookie-release-check.md)。

## 交付行为

所有在线 API 和 CLI 只从 Helper 获取完整快照；公共入口为 `infrastructure/helper/session_provider.py`。每个有界操作按账号串行，快照、版本及 Jar 仅在后端内存；结束或取消后清理。扫描循环每轮重新获取，轮次间释放锁。Web 启动不启动扫描。

`helper/client.py` 独立管理认证，仅连接配置地址。登录、快照和增量更新路径与配套 Helper 契约一致，401 最多一次重新认证，403/404 不重试。Helper 不使用闲鱼出站代理，其管理 Cookie 不进入闲鱼客户端。

`goofish/cookie_jar.py` 保留域、路径、有效期、HttpOnly、Secure、SameSite、分区和创建顺序；请求优先长路径，签名取对应页面可见的首个 Token。`mtop.py` 统一处理所有业务请求，每跳记录原接收时间及多条 Set-Cookie，提交 URL 去除查询和片段，失败正文、HTTP 错误和响应读取失败也先提交已收到的更新。重定向限五跳并限制 HTTPS 来源，超限更新立即停止。

回写成功采用新版本；`changed=false` 不等同在线验证通过；同步 `failed` 表示已保存，展示提醒而不重放。409、结果未知、契约错误等会销毁临时会话并停止分页、补全和扫描；下一次操作重新获取权威快照，禁止旧增量换版本重发。已确认的发现页、商家、目录、事件和候选保留。

网页移除 Cookie 粘贴/保存入口，展示 Helper 来源、目标账号、获取/提交时间、同步状态和暂停原因。重新检查会请求闲鱼，通过后才解除暂停。旧保存端点返回 410 `cookie_management_moved_to_helper`；所有在线 CLI 的 `--state` 明确报迁移错误。Reader 不读取旧 Cookie 文件、不自动上传或删除用户文件，不删除业务数据库。

## 验证

- 全量 `.venv/bin/pytest -q`：**267 passed**，另有两项既有 TestClient 依赖的弃用提示，不影响结果。
- 新增 `test_helper_cookie.py`：契约字段/路径、完整快照、权限、认证边界、秘密隔离、Cookie 顺序及作用域、删除/有效期、分区、原时间、多跳、失败头与正文、更新限制、版本推进、无变化、冲突、未知结果、同步失败、有限重试、操作串行、取消释放及逐轮获取。
- 新增 `test_helper_business.py`：Helper 异常停止后续请求、已确认发现进度恢复与入池去重、不写入未确认目录/事件/候选、旧文件保留、所有在线 CLI 废弃参数、无本地 fallback、无前端账号覆盖、Web 不启动扫描、验证后解除暂停。
- `tests/fixtures/helper_cookie_protocol.json`：依据已核对的 Helper `cookierefresh` 协议测试固定域/路径、创建顺序、精确删除和分区样本；Reader 离线复用同组输入和预期。
- `scripts/workbench_smoke.cjs`：Helper 界面、无旧输入、重新检查成功/失败、按钮恢复，以及商家、目录选品、候选来源、排除规则、扫描判断、桌面/移动端回归通过，无 JavaScript 错误。
- `scripts/product_detail_smoke.cjs`：目录跳转、详情字段、零值/未知、刷新、返回、验证提示、主图和桌面/移动端回归通过。
- Python 编译检查、所有 Web JavaScript 与浏览器脚本语法检查、模块依赖边界及 `git diff --check` 通过。

浏览器测试使用已有 Chromium、HTTP mock 和临时业务数据库。FastAPI TestClient 的线程唤醒及 Chromium 在受限沙箱中无法正常运行，因此在允许的本地环境执行；未使用真实 Cookie、未调用真实闲鱼。

## 保留的限制与上线前条件

Token 过期且响应已轮换页面可见 Token 时，确认回写后仅允许三个已知只读 API 重试一次。缺少 Token、未轮换或恢复仍失败时明确停止。本版未移植 Helper 的 IM Token 交换，不实现密码/扫码/静默登录或验证码自动化；真正 Session 失效与人机验证仍由 Helper 恢复。

并发锁只覆盖当前 Reader 进程；多个 Reader 进程或 Helper 后台更新依赖 Helper 的版本冲突检查，不宣称分布式锁或无限可用登录态。状态时间只在进程内保存，重启后重新检查；暂停标志和非敏感暂停原因沿用业务数据库 `meta`。

本次 Reader 验证依据固定契约和 mock，未部署 Helper、未进行真实服务联调。上线前需确认 Helper 两个交换接口已实现并验证、四项服务端配置正确、账号归属及已有续期启用条件满足、网络与时间同步正常。代码交付不包含生产部署，不新增定期扫描。

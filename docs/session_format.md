# Helper 登录态配置与迁移

所有在线 API 和 CLI 均使用 Helper，Reader 不再读取或保存本地 Cookie。

配置 `RADAR_HELPER_BASE_URL`、`RADAR_HELPER_USERNAME`、`RADAR_HELPER_PASSWORD`、`RADAR_HELPER_ACCOUNT_ID`。Helper 地址使用 HTTPS，受控同机回环允许 HTTP。账号必须归属于该 Helper 用户，并在 Helper 完成登录及既有续期配置；Reader 不会自动启用账号。

`radar auth check` 只确认完整快照可取得，`radar auth check --ping` 或网页“重新检查”才验证闲鱼在线请求，通过后解除暂停。`radar scan-pool --clear-auth-pause` 也先重新获取并在线检查，不直接清除暂停。

`--state` 已废弃，显式使用会报迁移错误。`POST /api/auth/session` 返回 410 `cookie_management_moved_to_helper`，不保存或上传请求中的 Cookie。旧 `data/state/*.json` 文件保留，不作为 fallback；用户确认迁移后可自行清理，代码不自动删除。业务数据库和已有发现、扫描进度不受影响。

每个有界操作按账号串行获取完整快照与不透明版本，在后端内存使用完整 Jar。每跳响应的原始 Set-Cookie 以数组、去查询参数的来源 URL 和原 UTC 接收时间回写 Helper，先确认回写才继续业务。操作结束清理临时会话，Helper 管理 Cookie 与闲鱼 Cookie 分属不同客户端。`RADAR_HTTP_PROXY` / `RADAR_HTTPS_PROXY` 只用于闲鱼请求。

回写 409 会丢弃旧增量；回写超时、连接中断、5xx 或无效成功响应均按结果未知停止，不盲目重发。下一次操作重新获取 Helper 权威状态。`runtime_sync_status=failed` 表示已保存，显示提醒而不重放。

Token 过期且响应已经轮换页面可见签名 Token 时，回写确认后最多重试原只读请求一次。缺少 Token、未轮换或重试仍失败时停止，提示在 Helper 恢复。本版不移植 Helper 的 IM Token 交换，不新增扫码、密码登录、静默登录、验证码自动化或定时续期。Session 失效、人机验证和限流不会通过换 Cookie 循环掩盖。

网页状态只显示 Helper 来源、账号、连接/暂停/同步状态和获取/提交时间，不返回 Cookie、管理会话、Token 前缀或凭据版本。`radar run` 仅在用户显式启动时运行，每轮重新获取并释放操作锁；启动 Web 不会启动扫描。

契约和验收依据见 `docs/helper-cookie-consumption-plan.md`。生产部署不包含在代码实施中。

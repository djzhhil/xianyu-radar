# Helper Cookie 发布检查

日期：2026-10-03。检查分支：`codex/helper-release-check`。Reader 接入提交为 `c6ba60b`，Helper production 源码为 `bb404bc`。开始检查时 Reader 工作区干净，接入分支与 main 指向同一提交。本记录覆盖代码和发布前验证，不包含生产部署。

## 审查与修正

对照 Helper `internal/server/cookie_exchange_handlers.go` 与 `api/openapi.yaml`，两个交换接口均已注册。核对 Reader 的独立管理登录、快照获取、增量回写、临时 Jar、在线入口及停止错误处理，未发现在线本地 Cookie fallback。

修正 Reader 的契约前置校验：版本严格采用 `v1:` 加 64 位小写十六进制；快照与回写结果也检查版本。回写时间必须是 UTC 三位毫秒，批次时间非递减，保留原接收时间；仅接受约定主机及默认 HTTPS 端口，禁止 query/fragment（包括空查询）；拒绝空 Set-Cookie、CR/LF、未知字段与缺失字段。保留时间窗口、批次数量、UTF-8 字节体积限制。无效输入在发送前停止并返回既有结构化错误，不暴露原始凭据。

测试样本改用 Helper 实际接受的版本形状，并新增非法格式、批次倒序、URL、响应头及合法边界回归。

## 检查结果

- 全量离线业务回归：**284 passed**，覆盖契约、并发、错误处理及原有业务；两条既有 TestClient/anyio 依赖弃用提示不影响结果。
- 工作台浏览器回归：PASS，包含 Helper 状态、商家、目录、候选、排除、扫描判断及桌面/移动端，无 JavaScript 错误。
- 商品详情浏览器回归：PASS，包含导航、字段、刷新、验证提示、图片及桌面/移动端。
- Python 编译、Web JavaScript 与浏览器脚本语法检查及 `git diff --check`：通过。
- 从当前跟踪源码复制到临时干净目录，借用系统已有 wheel 构建器离线构建 wheel/sdist：通过。包中包含 Helper 客户端、Session Provider、数据库 schema 与迁移，不包含已移除的旧本地会话模块。构建日志位于 `/tmp/radar-release-build.log`；不使用工作区历史 build 缓存。
- 当前打包配置不收录 `web/` 静态资源，因此 wheel/sdist 不能作为完整 Web 服务发布物。完整 Web 发布沿用 README 的源码安装方式并保留 `web/`；本次不扩展打包架构。

测试均使用 mock、已有 Chromium 和临时数据库。未使用真实 Cookie；未修改、上传或删除用户旧文件及业务数据库，未启动定期扫描。

正式部署方式已确定为固定提交的完整源码部署，使用独立虚拟环境、systemd 和共享数据目录，详见 [正式部署方案](production-deployment-plan.md)。

## 上线前尚需完成

当前进程没有配置 `RADAR_HELPER_BASE_URL`、`RADAR_HELPER_USERNAME`、`RADAR_HELPER_PASSWORD`、`RADAR_HELPER_ACCOUNT_ID`。因此本次不能验证真实服务登录、目标账号归属、完整快照及实际 Set-Cookie 回写；Helper production 源码具备接口不等于运行中的服务已部署该版本。

实际发布前应在目标运行环境核实上述服务端配置、Helper 运行版本、网络与时间同步，以及账号已有续期条件，然后完成搜索、商品详情、商家商品列表的真实请求与回写验证，检查新的版本及 runtime_sync_status。真实登录失效或风控仍由 Helper 恢复，Reader 的恢复限制保持原验收记录所述。

结论：本地代码与离线发布检查完成后可交付源码候选；真实联调条件尚未满足，不宣称生产上线通过。未执行推送或生产部署。

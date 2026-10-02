# 前端工作台维护与验收

前端沿用静态 HTML、CSS 和 JavaScript，无需 npm 才能运行。`radar serve` 直接提供页面和本地图标资源。

## 布局与交互

- 默认打开商家池；导航分为商家、候选、扫描变化、发现和登录设置，当前页面写入 URL 片段。
- 商家列表和商家详情分别展示。详情内有商品目录、备注标签、入池来源三个视图，返回时保留商家列表。
- 全局计数与候选范围统计分别展示，候选行的商品信息和审核操作分列。
- 时间显示为北京时间；诊断响应保留原始内容。
- 移动端采用可滚动导航和表格，页面本身不得横向溢出。

## 图标资源

`web/icons-source.js` 仅导入所用 Lucide 图标；`web/icons.js` 是提交到仓库的打包产物，运行时不请求 CDN。版权许可在 `web/LICENSE-lucide.txt`。

修改图标后重新生成：

```bash
npm install --prefix /tmp/radar-ui-tools lucide@1.50.0 esbuild@0.28.2 --ignore-scripts --no-audit --no-fund
NODE_PATH=/tmp/radar-ui-tools/node_modules /tmp/radar-ui-tools/node_modules/.bin/esbuild web/icons-source.js --bundle --minify --format=iife --outfile=web/icons.js --legal-comments=eof
```

页面上的图标按钮提供 `aria-label` 和悬停名称。异步按钮用原始节点恢复内容，避免忙碌状态结束后丢失图标。

## 浏览器验收

`scripts/workbench_smoke.cjs` 会启动临时数据库和测试 Web 服务，结束后停止该服务；测试商品、候选及审核操作均在临时库完成，不读取真实登录态，不调用闲鱼。

```bash
npm install --prefix /tmp/radar-ui-tools playwright@1.63.0 --ignore-scripts --no-audit --no-fund
/tmp/radar-ui-tools/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/radar-ui-tools/node_modules node scripts/workbench_smoke.cjs
```

也可用 `RADAR_BROWSER_PATH` 指定已有 Chromium 可执行文件，用 `RADAR_UI_ARTIFACT_DIR` 指定截图目录；默认截图位于 `/tmp/xianyu-radar-workbench`。测试服务使用本机 `18766` 端口，占用时应先选用空闲测试端口，而不是关闭现有服务。

覆盖：商家添加与重复添加、暂停状态、详情视图、备注保存与重载、目录筛选分页、主图正常/失效/缺失、候选筛选和审核、刷新后图标保留、URL 片段切换、桌面与移动端五个页面的宽度、JavaScript 错误。

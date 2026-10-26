# 就地帮助验收（2026-10-26）

## 完成范围
六个主页面及高级配置面板增加问号帮助，包含资产参数与引用、请求/断言/等待、身份/项目、调度、统计口径、运行状态与证据、资源租约、覆盖/评估历史。明显的名称、刷新和分页保持简洁。

实现：common/HelpHint.vue 负责交互，content/helpTopics.ts 负责类型化共享文案。字段和原操作保留可访问名称；帮助按钮名称以“查看帮助：”开头。说明包含用途、示例、前置条件及操作影响；查询筛选与资产编辑、实际耗时与执行预算使用不同说明。

## 验证结果
- npm run build --prefix platform/frontend：TypeScript 与生产构建通过。
- node tests/frontend/reliability.cjs：通过。
- PYTA_RUN_BROWSER_TESTS=1 PYTA_BROWSER_EVIDENCE_DIR=/tmp/pyta-help-evidence .venv/bin/python -m pytest tests/backend/test_platform_frontend_browser.py -q -s：1 passed，页面脚本错误 0。
- 原有创建/保存/预检/发布/本地真实 HTTP 运行/诊断/固定套件引用贯通，断开 API 后显示明确错误。
- 悬停可见并可移入浮层；焦点关联 aria-describedby；Escape 关闭；手机点击展开/再次点击和外部点击关闭。
- 帮助交互不产生 POST/PATCH/DELETE、不切换 checkbox、不展开所在 summary。
- 六路由九宽度，逐页实际悬停第一处帮助并验证浮层四边界，再检查默认/高级配置两状态；108 组布局断言通过。
- git diff --check 通过。最终查询筛选和耗时帮助文案细化后重新通过生产构建、类型与可靠性检查。

## 审查与修正
- 新问号会扩展表头最小宽度，覆盖账本原始 table 在 390px 溢出。改用现有 table-shell 局部滚动，保留完整表格数据。
- 给字段/静态标题保留明确可访问名称，防止帮助按钮混入原控件名称；避免前缀定位器匹配到问号。
- 监听页面滚动时跟随可见锚点，避免原生自动滚动把刚展开的帮助关闭；浮层自身滚动不关闭。
- 问号与状态/操作按钮同组，修正 Grid 中垂直错位和 space-between 拉开图标的问题。
- 人工检查桌面悬停、手机点击、调度与首页截图；本文同目录保留两张帮助截图，其余回归截图在 /tmp/pyta-help-evidence。

## 范围限制
验证使用本地隔离 SQLite 和本地 /check，没有调用公司业务或数据库。没有部署到线上；前端代码和测试保留在工作区，已有业务改动未合并提交。

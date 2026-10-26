# 工作台 UI 验收（2026-10-26）

## 范围与结果
- 六个主页面：仪表盘、用例、套件、环境、执行结果、调度。
- 生产构建与 TypeScript 检查通过；前端可靠性检查通过。
- 真实浏览器创建场景 → 保存 → 预检 → 发布 → 提交本地真实 HTTP 运行 → 诊断成功；随后通过页面创建引用固定场景版本的套件。
- 搜索空态、清空搜索、选中状态、取消放弃未保存输入、高级选项展开/关闭、断开 API 后显示错误均通过。
- 复用 tests/frontend/responsive-layout.mjs 的 widths/routes/measureLayout/assertLayout：六路由 × 九视口 × 默认/展开两状态，共 108 次布局断言通过；页面脚本错误 0。
- 320、390、768、960、980、1080、1081、1280、1440px，保留非空资产、发布版本与运行证据。
- 截图在 390、980、1440px 保存，默认状态截图均回到页首；人工审查桌面六页面与手机用例/套件布局。

## 命令
```sh
npm run build --prefix platform/frontend
node tests/frontend/reliability.cjs
PYTA_RUN_BROWSER_TESTS=1 PYTA_BROWSER_EVIDENCE_DIR=/tmp/pyta-ui-evidence .venv/bin/python -m pytest tests/backend/test_platform_frontend_browser.py -q -s
git diff --check
```

最终浏览器结果：1 passed；created_published_run=true、live_http_evidence=true、offline_error_visible=true、page_errors=[]、layout_checks=108。
浏览器环境最初缺少已安装 Playwright 对应的 Chromium Headless Shell，已通过其官方安装命令补齐。

## 证据与限制
- 本目录的 1440-cases-default.png、390-cases-default.png 为提交的桌面/手机视觉证据，其余截图本地保留。
- 本地隔离 SQLite 与本地 /check，不连接公司数据库，不调用公司业务接口。
- 线上 /cases 返回访问认证 401；没有远端部署或远端新产物验收。
- 工作区原有未提交业务变更保持；本轮只对规范、复盘和验收证据独立提交，前端代码留在工作区。

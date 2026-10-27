# PytestAutoApi 前端

这是个人接口测试工作台，使用 Vue 3、TypeScript、Pinia、Vue Router 和 Element Plus（中文界面）。

## 使用平台

运行中的平台左侧提供“使用手册”，从 HTTP/JSON 基础开始，按环境、目标、身份、场景、套件、调度和结果排查逐层讲解。字段旁问号提供短说明，点击“查看完整手册”在新标签页打开对应小节，原页面的未保存配置保留。

日常主线是：配置环境与目标 → 编写请求和断言 → 调试当前草稿 → 保存、预检和发布版本 → 固定版本运行或编排套件 → 查看结果及失败证据。调试会真实发请求，不自动保存或发布；正式套件与调度引用固定发布版本。

界面与验收以桌面浏览器为目标。按用户于 2026-10-27 确认的范围，后续不再要求手机兼容。

## 工作区操作

- 用例：左侧搜索场景与选择步骤，中间编辑当前请求，通过参数、请求头、请求体、断言、变量提取、高级设置标签切换；调试结果就近显示。
- 草稿编辑、场景/套件设置、发布与版本、正式运行分区；保存和调试始终在工作区工具栏。保存检查全部步骤，隐藏配置中的错误会自动定位。
- 环境、目标、身份、项目绑定从环境页顶部切换；套件和调度使用单一主目录，保留未保存编辑确认。
- 执行结果采用列表与详情并排布局，常用状态/环境筛选常显；关键词明确只查当前页。
- 扩展工具通过四个具名标签进入；手册及问号保留精确小节与新标签页。

通用输入和选择器在 `src/components/ui/controls.ts` 接入 Element Plus：保留旧编辑器的 Event 处理边界、数值类型、可检索选项和表单必填约束。库组件在应用入口显式注册，页面和手册延迟加载；业务范围确认统一使用 `confirmAction`，取消返回 false。

## 本地开发

本机已有依赖和配置时，在项目根目录执行 `./start.sh` 即可一起启动前后端；`./start.sh --check` 仅检查，Ctrl+C或另一个终端执行 `./stop.sh` 停止本次进程。默认读取 `~/.config/pytestautoapi/` 中的平台与业务环境文件，具体说明见[项目启动入口](../../README.md#本地启动)。

仅启动前端或首次安装时，可使用下面的独立命令：

先按 [启动指南](../../docs/new-architecture-quickstart.md) 启动后端，再在项目根目录执行：

```bash
npm install --prefix platform/frontend
npm run dev --prefix platform/frontend
```

默认打开 `http://127.0.0.1:5173`。Vite 将 `/api` 转发到本地后端 `http://127.0.0.1:8000`，默认使用相对 API 地址 `/api/v1`。通常不需要修改接口地址；后端端口不同时，在 `platform/frontend/.env.local` 设置：

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_DEV_PROXY_TARGET=http://127.0.0.1:9000
```

接口失败显示真实错误，空数据库显示空态，不提供替代业务数据。秘密值由服务端准备，不能写入前端环境变量、手册或公开配置。

## 目录

| 位置 | 职责 |
| --- | --- |
| `src/router` | 页面路由、标题、导航区及手册小节定位 |
| `src/pages` | 工作台、用例、套件、环境、结果、调度、扩展工具和手册 |
| `src/components` | 编辑器、调试、断言、证据、公共问号及手册图形组件 |
| `src/content/helpTopics.ts` | 类型化短帮助文案 |
| `src/content/manual` | 手册正文、分级目录、主题小节映射、解析和搜索 |
| `src/stores` | 壳层导航、最近资产 ID 等共享状态 |
| `src/api` | 真实后端 API 调用与返回数据适配 |

编辑缓冲、已保存草稿与调试快照相互独立。浏览器最近资产只记忆 ID，不保存请求内容或凭证。

## 构建与检查

在项目根目录执行：

```bash
npm run build --prefix platform/frontend
node tests/frontend/reliability.cjs
node tests/frontend/manual-content.mjs
```

构建包含 TypeScript 检查。手册检查加载实际正文与运行时，校验主题映射、小节、站内链接和关键词查找；浏览器回归额外验证实际 SVG、页面操作、新标签页和草稿保护。

```bash
PYTA_RUN_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/backend/test_platform_frontend_browser.py -q -s
```

浏览器回归使用隔离本地 API 和合成测试数据，不调用公司业务。桌面布局检查宽度为 1280/1440/1920px。构建成功不替代操作验收，本地通过不表示已部署。

新增手册文章、字段或帮助主题时，同时维护稳定文章/小节 ID、主题映射和示例；详细规则见 [使用手册契约](../../.trellis/spec/frontend/user-manual.md)。

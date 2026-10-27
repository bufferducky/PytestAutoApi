# platform 目录说明

`platform/` 是 PytestAutoApi 的页面工作台与管理服务。日常资产在页面维护，后端负责版本、环境、运行和调度，独立 [testflow_engine](../src/testflow_engine/README.md) 执行标准化测试。

## 页面入口

| 页面 | 日常操作 |
| --- | --- |
| `/dashboard` 工作台 | 查看回归情况，继续编辑或处理失败 |
| `/cases` 用例管理 | 编辑步骤、断言和提取；调试草稿；保存、预检和发布版本；按内容导入旧 YAML |
| `/suites` 套件管理 | 组合已发布场景，固定版本和顺序 |
| `/environments` 环境管理 | 配置环境、目标、身份和项目绑定 |
| `/runs` 执行结果 | 查看失败证据、资源与清理状态，取消运行或关联复跑 |
| `/schedules` 调度任务 | 创建持久计划、预览时间、启停及查看触发记录 |
| `/extensions` 扩展工具 | 查看覆盖、测试资源、旅程能力及历史评估 |

草稿调试使用当前未保存内容，支持整场景和单步骤；缺少前置输出时须提供本次 inputs。正式回归使用已发布版本，调试记录不计入正式统计或发布证据。新运行显式使用 `transport_mode=live`。

## 前后端职责

- [frontend](frontend/README.md)：Vue 3、TypeScript、Pinia 与 vue-router；展示真实数据与错误，空库显示空态。
- [backend](backend/README.md)：FastAPI、MySQL 仓储和后台执行；`WorkerHost` 消费运行任务，`ScheduleHost` 扫描持久化计划。后端保存运行、环境和版本快照及脱敏证据。

浏览器、移动端和评估代码保留在扩展能力范围。旅程运行须通过驱动、浏览器或设备预检；新评估执行禁用，历史仍可读取，不能据代码存在推断真实业务或真机已验收。

## 启动与验证

先按 [启动指南](../docs/new-architecture-quickstart.md) 安装 [pyproject.toml](../pyproject.toml) 依赖、配置独立 MySQL 并执行 Alembic。在仓库根目录的两个终端分别运行：

```bash
# 后端终端先激活 .venv 并设置数据库环境变量
make backend-dev
```

```bash
make frontend-dev
```

默认前端 `http://127.0.0.1:5173`，后端 `http://127.0.0.1:8000`。现有 [Vite 配置](frontend/vite.config.ts) 将 `/api` 代理到后端；`VITE_API_BASE_URL` 默认 `/api/v1`，可用 `VITE_DEV_PROXY_TARGET` 覆盖代理目标。

先检查 `GET /api/v1/health/live`，再打开工作台、用例与执行结果页面。创建自己的测试场景后完成一次“调试 → 保存 → 预检 → 发布 → 真实运行 → 查看结果”。构建检查用 `make frontend-build`，后端与引擎回归用 `make test-new`；部署见 [部署说明](../deploy/README.md)。

# PytestAutoApi 日常回归工作台

PytestAutoApi 以页面交互维护测试资产：编辑请求步骤、调试草稿、发布场景版本、组合套件、执行回归和查看失败证据。Vue 前端、FastAPI 后端与独立 `testflow_engine` 配合，平台状态持久化到 MySQL。

## 日常使用

1. **环境管理**：配置环境、目标系统、测试身份与项目绑定。秘密由后端运行环境注入，页面只保存秘密引用。
2. **用例管理**：编辑请求、断言、变量提取和步骤依赖；可调试未保存的整场景或单步骤。调试记录独立标记，不作为正式回归或发布证据。
3. **正式回归**：保存草稿 → 预检 → 发布不可变版本 → 选择环境及构建 → 执行。套件固定已发布场景版本和执行顺序。
4. **执行结果**：查看运行状态、失败步骤、预期与实际差异、脱敏请求响应及清理证据；支持取消和关联复跑。
5. **调度任务**：配置持久化计划、预览触发时间、启停任务和查看执行记录。

新运行显式使用 `transport_mode=live`，页面连接真实后端；空库显示空态，连接失败显示错误。

## 本地启动

在仓库根目录准备 Python 3.9+、Node.js 22.12+ 和独立 MySQL 数据库：

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-dev
npm ci --prefix platform/frontend
```

依赖统一维护在 [pyproject.toml](pyproject.toml)。配置 `PLATFORM_BACKEND_DATABASE_URL`（`mysql+pymysql`）或 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` 后，在同一终端执行：

```bash
python -m alembic -c platform/backend/alembic.ini upgrade head
make backend-dev
```

另一终端在仓库根目录运行 `make frontend-dev`，打开 `http://127.0.0.1:5173`。Vite 默认将 `/api` 代理到 `http://127.0.0.1:8000`。完整配置、页面验证和故障排查见 [启动指南](docs/new-architecture-quickstart.md)。

## 目录与边界

| 入口 | 职责 |
| --- | --- |
| [platform/frontend](platform/frontend/README.md) | 页面、表单与结果展示 |
| [platform/backend](platform/backend/README.md) | 资产、环境、运行、MySQL 仓储、worker 与持久调度 |
| [src/testflow_engine](src/testflow_engine/README.md) | 标准模型、真实 HTTP、断言、插件和旧 YAML 兼容 |
| [tests](tests/) | 引擎、兼容层与平台回归测试 |
| [Files/test-media](Files/test-media/) | 保留的测试媒体 |

旧脚本框架、业务样例及旧截图已清理。页面仍支持按内容导入旧 YAML，独立兼容层继续保留；导入后须核对请求、断言和依赖，再预检发布。浏览器与移动端旅程代码保留，依赖、设备和业务验收需分别准备；新评估执行禁用，历史报告仍可查询。扩展能力不代表完整业务、真机或模型质量已验收。

## 验证与参考

```bash
make test-new
make frontend-build
```

离线测试通过不等于真实 MySQL、业务接口或设备验收通过。部署与历史数据迁移见 [部署说明](deploy/README.md) 和 [MySQL 迁移手册](docs/mysql-migration.md)；代码阅读入口见 [开发导览](docs/getting-started-modernized.md)。

项目源自余少琪的接口自动化框架。保留 [原项目](https://gitee.com/yu_xiao_qi/pytest-auto-api2)、[作者博客](https://blog.csdn.net/weixin_43865008)、[历史版本记录](https://gitee.com/yu_xiao_qi/pytest-auto-api2/wikis/Home)、[1.0 文档](https://blog.csdn.net/weixin_43865008/article/details/121903028?spm=1001.2014.3001.5502) 和 [历史示例 API 参考](https://wanandroid.com/blog/show/2)；这些链接用于来源与历史参考，当前启动方式以本仓库说明为准。

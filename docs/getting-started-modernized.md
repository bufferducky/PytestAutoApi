# PytestAutoApi 开发导览

第一次运行请按 [启动指南](new-architecture-quickstart.md) 配置依赖、MySQL 和 Alembic，再分别执行 `make backend-dev` 与 `make frontend-dev`。本文用于定位代码与当前能力。

## 产品主路径

日常从页面配置环境和身份、编辑场景步骤、调试草稿、保存预检并发布版本，再执行正式回归。套件固定版本，调度触发回归，执行结果提供失败与清理证据。新运行显式使用 `transport_mode=live`；草稿调试独立标记，不计入正式统计或发布证据。

平台状态持久化到独立 MySQL，结构升级使用 Alembic。`pyproject.toml` 是 Python 依赖入口，Vite 开发代理将 `/api` 转发到后端。完整参数和命令集中在启动指南，避免多份配置说明失去同步。

## 代码地图

| 位置 | 职责与阅读入口 |
| --- | --- |
| [platform/frontend](../platform/frontend/README.md) | 页面交互；从 [router/index.ts](../platform/frontend/src/router/index.ts) 找到页面与 API 模块 |
| [platform/backend](../platform/backend/README.md) | 管理与编排；从 [app.py](../platform/backend/src/pyta_platform_backend/app.py) 查看服务、worker 和 schedule host 装配 |
| [src/testflow_engine](../src/testflow_engine/README.md) | 执行内核；从 [models/core.py](../src/testflow_engine/models/core.py) 和 [executor/engine.py](../src/testflow_engine/executor/engine.py) 理解输入、执行与结果 |
| [tests/engine](../tests/engine/) / [tests/compat](../tests/compat/) / [tests/backend](../tests/backend/) | 引擎行为、旧 YAML 转换与平台回归 |
| [Makefile](../Makefile) / [pyproject.toml](../pyproject.toml) | 开发命令、打包与依赖 |

实际运行链路为：页面提交 → 后端编译定义并保存运行与投递记录 → `WorkerHost` 消费 → 引擎执行 → 持久化结果 → 页面查询。`ScheduleHost` 扫描持久化计划并创建运行。长任务在后台执行，HTTP 受理成功不表示测试通过。

## 兼容与后续能力

- 旧脚本框架与业务样例已清理；页面保留旧 YAML 内容导入，[独立兼容层](../src/testflow_engine/compat/legacy_yaml.py) 继续将其转换为标准模型。导入后需核对请求、断言、依赖及未支持项，不要求恢复旧目录。
- 浏览器与移动端旅程代码保留。驱动、浏览器基线、设备、应用构建和业务场景需逐项准备与验收，代码存在不等于整套能力已成熟。
- 新评估执行禁用，历史报告仍可查询；保留代码和 [测试媒体](../Files/test-media/) 供后续建设，不作为当前模型质量验收结果。

## 验证与参考

在根目录激活虚拟环境后，用 `make test-new` 验证引擎、兼容与后端，`make frontend-build` 检查类型和生产打包。离线检查与真实数据库、业务接口和设备验收分别记录。

[部署说明](../deploy/README.md) 与 [MySQL 迁移手册](mysql-migration.md) 说明部署和历史数据保护。[架构演进设计](architecture-modernization.md) 保留设计背景，早期阶段描述应结合当前启动指南和实际代码阅读。

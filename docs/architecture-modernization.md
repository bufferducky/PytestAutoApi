# PytestAutoApi 平台架构

当前产品以网页工作台维护测试资产、触发执行和查看证据。旧 `run.py` 脚本框架、旧业务示例与 Allure 教程资料已于 2026-10-27 移除。

## 职责边界

```text
Vue 工作台 → FastAPI 路由 → 业务服务 → MySQL 仓储
                                ↓
                         持久任务 / outbox
                                ↓
                         WorkerHost → 执行引擎
                                ↓
                         逐步证据、状态、附件
                                ↓
                           网页查询与排障
```

- `platform/frontend/src/`：用例、套件、环境、运行、调度及扩展页面。
- `platform/backend/src/pyta_platform_backend/api/`：请求校验与 HTTP 协议，路由委托服务编排。
- `services/`：资产草稿与发布、场景编译、上下文、运行、资源、诊断与调度。
- `repositories/`、`db/`：SQL 仓储、事务、连接管理和 schema；生产升级由 Alembic 完成。
- `workers/`：持久任务领取、后台执行、取消、重启恢复和结果写回。
- `runners/`：浏览器、移动端旅程和评估相关适配，保留现有能力边界，后续再完善。
- `integrations/yanji/`：言迹系统查询接入包和脱敏契约资料；具体业务资源随后端交付，通用引擎保持独立。
- `src/testflow_engine/`：标准执行模型、HTTP 传输、变量渲染、断言、等待与插件。

API 请求负责登记和投递，长任务在后台消费。当前应用在同一进程启动 API、WorkerHost 和 ScheduleHost，部署保持单 worker；这不等于独立分布式任务队列。

## 数据与运行

开发和生产显式配置 MySQL；未配置时启动失败。离线 SQLite 只供测试和历史导入，平台不会自动回退。附件由独立 artifact root 管理。

新执行显式使用 live，不提供产品 Mock 或默认演示目录。资产使用草稿与不可变发布版本，任务绑定具体版本与上下文快照。状态和结果按真实证据记录，历史模拟数据不计作真实业务通过。

持久调度由 `services/schedule_service.py` 中的 ScheduleService / ScheduleHost 管理。旧 LightweightScheduler 装配已移除。

## YAML 兼容

页面仍支持粘贴旧 YAML，后端通过独立 `compat/legacy_yaml.py` 转为标准模型与草稿。未映射字段保留在迁移报告中，需要处理阻塞后发布；导入本身不发送业务请求。

仓库不再自带旧业务 `data/` 示例，兼容回归使用 `tests/fixtures/legacy_yaml/` 的合成输入。已有按路径读取 `data/` 的兼容 API 仍要求部署方显式提供受控文件；日常使用优先走页面内容导入。平台状态库的 SQLite 历史迁移由独立 `migrate_sqlite` 工具完成，与旧 YAML 脚本框架无关。

## 保留与验证边界

浏览器、移动端旅程、媒体与评估代码保留，评估新执行仍被禁用。保留代码不代表已完成真实业务验收。历史数据库和附件不属于源码清理目标。

- 后端回归：`tests/backend/`。
- 引擎回归：`tests/engine/`。
- YAML 转换与缓存兼容：`tests/compat/`。
- 前端交互脚本：`tests/frontend/`。

真实 MySQL 和浏览器集成需要相应测试配置；离线通过不能替代真实环境验收。

启动见 [快速开始](new-architecture-quickstart.md)，部署见 [部署说明](../deploy/README.md)，清理依据见 [审查记录](../platform/backend/CLEANUP-AUDIT.md)。

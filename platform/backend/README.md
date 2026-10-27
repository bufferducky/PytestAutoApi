# 平台后端

后端管理资产、环境、调度和运行记录，由后台 worker 调用 `src/testflow_engine/` 执行测试。HTTP 请求只创建、投递和查询任务，不同步执行长任务。

## 启动与验证

在仓库根目录安装现代化依赖，配置 MySQL 后执行：

```bash
source .venv/bin/activate
# 设置 PLATFORM_BACKEND_DATABASE_URL，或 MYSQL_HOST/PORT/USER/PASSWORD/DATABASE。
python -m alembic -c platform/backend/alembic.ini upgrade head
make backend-dev
curl http://127.0.0.1:8000/api/v1/health/live
curl http://127.0.0.1:8000/api/v1/dashboard/overview
```

开发和生产必须使用 `mysql+pymysql`；缺少配置会启动失败，不回退本地 SQLite。只有 `app_env=test` 允许离线 SQLite 测试存储。附件路径由 `PLATFORM_BACKEND_ARTIFACT_ROOT` 配置，默认 `.runtime/artifacts`。

完整部署配置见 [部署说明](../../deploy/README.md)，初次安装见 [快速开始](../../docs/new-architecture-quickstart.md)。

## 运行边界

- 新运行必须显式指定 `execution_mode=standard_run/legacy_yaml` 和 `transport_mode=live`；不提供产品 Mock 执行。
- 场景和套件目录来自持久化资产，不自动初始化演示目录。
- 演示套件列表为空；演示运行、导入和 seed 入口已退役，写入返回 410。
- 新评估执行被禁用，历史记录仍可查询。
- `WorkerHost` 负责后台消费、互斥和恢复；`ScheduleHost` 扫描持久化调度计划。
- 旧 `scheduler/` 骨架、`create_app(scheduler=...)` 参数和 `app.state.scheduler` 已移除；调度统一由 `app.state.schedule_host` 管理。
- 历史 SQLite 导入由 `pyta_platform_backend.migrate_sqlite` 完成；迁入运行不会自动恢复执行。

## 目录与阅读顺序

1. `src/pyta_platform_backend/main.py`：ASGI 入口。
2. `app.py`：服务装配与 worker/schedule host 生命周期。
3. `config.py`：环境变量与数据库、附件路径配置。
4. `api/router.py`、`api/routes/`：HTTP 协议与路由注册。
5. `services/`：资产、上下文、运行与调度编排。
6. `repositories/`、`db/`：持久化仓储、连接和 schema；Alembic 管理生产结构升级。
7. `workers/run_worker.py`、`runners/`：RunWorker 任务消费、引擎集成和执行适配。
8. `integrations/yanji/`：言迹查询接入包与随发布源码交付的脱敏契约资料。

包名是 `pyta_platform_backend`，避免与 Python 标准库 `platform` 冲突。`InMemory*Repository` 仍是 SQL 仓储的基类；`serialization.py` 提供多个 SQL 仓储共用的序列化函数；旧 `sqlite_support.py` 仅作兼容导出。

## 测试

```bash
.venv/bin/python -m pytest tests/backend -q
.venv/bin/python -m pytest tests/engine tests/compat tests/backend -q
.venv/bin/ruff check platform/backend/src --select F
```

离线测试通过不代表已验证真实 MySQL。MySQL 集成测试需要专用的 `PYTA_TEST_MYSQL_URL`，临时库名只允许 `pyta_validation*`，不可指向业务库。

清理依据和保留项见 [后端清理审查](./CLEANUP-AUDIT.md)。

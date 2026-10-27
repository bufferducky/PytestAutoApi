# Directory Structure

> How the **modernized** backend code is organized in this repository.

---

## Overview

This project is no longer just a legacy pytest automation framework.
It is becoming a split architecture with:

- an execution engine
- a platform backend
- a platform frontend
- compatibility bridges for legacy YAML assets

The most important rule is:

> **Do not mix platform orchestration code and engine execution code in the same layer.**

---

## Repository Layout

```text
PytestAutoApi/
├── pyproject.toml
├── src/
│   └── testflow_engine/
│       ├── models/
│       ├── executor/
│       ├── assertions/
│       ├── plugins/
│       ├── reporting/
│       └── compat/
├── platform/
│   ├── backend/
│   │   └── src/
│   │       └── pyta_platform_backend/
│   │           ├── api/
│   │           ├── repositories/
│   │           ├── db/
│   │           ├── runners/
│   │           ├── integrations/
│   │           ├── schemas/
│   │           ├── services/
│   │           └── workers/
│   └── frontend/
│       └── src/
├── tests/
│   ├── backend/
│   ├── engine/
│   ├── compat/
│   └── fixtures/legacy_yaml/  # synthetic compatibility input
└── Files/test-media/         # retained media fixtures
```

---

## Ownership Boundaries

### `src/testflow_engine/`

Put code here when the logic answers:

> "How do we execute a standardized test run or test case?"

Examples:

- request rendering
- transport abstraction
- assertion evaluation
- plugin hooks
- legacy YAML conversion to standard models

Do **not** put platform CRUD, API routing, or web request handling here.

### `platform/backend/src/pyta_platform_backend/api/`

Put code here when the logic answers:

> "What HTTP contract does the platform expose?"

Examples:

- `/runs`
- `/runs/{id}`
- `/dashboard/overview`

Routes should stay thin and delegate orchestration to services.

### `platform/backend/src/pyta_platform_backend/services/`

Put code here when the logic answers:

> "How do we orchestrate repositories, workers, and API-facing operations?"

Examples:

- create run + dispatch
- list runs
- update run status
- build dashboard overview data

Services are allowed to call repositories and worker boundaries.

### `platform/backend/src/pyta_platform_backend/repositories/`

Put code here when the logic answers:

> "How do we store or retrieve backend records?"

平台状态由 SQL 仓储持久化至 MySQL。InMemory 基类仍被 SQL 仓储复用；测试可显式使用 SQLite，生产结构由 Alembic 升级。

### `platform/backend/src/pyta_platform_backend/workers/`

Put code here when the logic answers:

> "How do we consume dispatched tasks and execute them outside the API request lifecycle?"

Examples:

- dispatcher boundary
- RunWorker task consumption
- future execution adapters calling `testflow_engine`

Do **not** run long execution directly in route handlers.

### 具体业务接入

`integrations/<system>/` 集中具体被测系统的接入包与脱敏资源。言迹查询包在 `integrations/yanji/query_pack.py`，JSON 在 `integrations/yanji/data/`；通过包资源读取，不放进通用引擎，也不依赖 docs 源码树。移动资源时验证隔离发布目录中的 API 与导入输出。

通用 worker 正式入口为 `workers.run_worker.RunWorker`，JSON/时间序列化为 `repositories.serialization`。旧 `workers.runner.MemoryWorkerRunner`、`repositories.sqlite_support`、`services.yanji_regression` 只作兼容重导出。正式仓储包导出 Sql*Repository，旧 Sqlite* 名保留别名。应用内部调用 `resolve_database_url()`。

### 调度

`services/schedule_service.py` 的 `ScheduleService` 与 `ScheduleHost` 管理持久计划及扫描生命周期，通过运行服务创建任务。旧 `scheduler/` 包和 `create_app` 的 `scheduler` 注入参数已移除。

---

## Tests Placement

### `tests/backend/`

Use for:

- route registration
- backend service behavior
- repository behavior
- worker status writeback

### `tests/engine/`

Use for:

- execution flow
- request rendering
- transport behavior
- assertion behavior
- plugin behavior

### `tests/compat/`

Use for:

- legacy YAML shape compatibility
- execution-level compatibility of representative historical assets

If a legacy asset can be parsed but not executed, add a test that states that limitation explicitly.

---

## Forbidden Structure Drift

Avoid these patterns:

- 重新引入已退役的根目录脚本框架；兼容输入仅放 tests/fixtures，不作为产品默认资产
- putting execution details directly inside FastAPI routes
- importing the top-level Python package as `platform.*`
- storing migration-only metadata in the frontend when it belongs in engine/backend layers

---

## Current Most Important Paths

If you need to orient yourself quickly, start here:

1. `/Users/ys/PycharmProjects/PytestAutoApi/src/testflow_engine/executor/engine.py`
2. `/Users/ys/PycharmProjects/PytestAutoApi/src/testflow_engine/compat/legacy_yaml.py`
3. `/Users/ys/PycharmProjects/PytestAutoApi/platform/backend/src/pyta_platform_backend/app.py`
4. `/Users/ys/PycharmProjects/PytestAutoApi/platform/backend/src/pyta_platform_backend/services/run_service.py`
5. `/Users/ys/PycharmProjects/PytestAutoApi/platform/backend/src/pyta_platform_backend/workers/run_worker.py`

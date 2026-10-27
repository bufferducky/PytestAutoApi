# Backend Development Guidelines

> Backend conventions for the **modernized** architecture in this repository.

---

## Overview

项目当前只保留页面交互平台与独立执行引擎：

- `src/testflow_engine/`：执行、断言、插件和 YAML 导入兼容。
- `platform/backend/src/pyta_platform_backend/`：FastAPI、MySQL、worker 和持久调度。
- `tests/backend/`、`tests/engine/`、`tests/compat/`：回归测试。
- `tests/fixtures/legacy_yaml/`：独立合成兼容输入。

2026-10-27 已移除旧 `run.py/common/utils/test_case` 脚本框架及业务示例、Allure 报告。旧 YAML 内容导入继续服务前端；浏览器、移动端旅程和评估模块保留现有边界。实际调度入口是 `services.schedule_service.ScheduleHost`。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Modern backend package layout and ownership boundaries | Active |
| [Database Guidelines](./database-guidelines.md) | 旧 SQL 工具退役说明 | Retired |
| [MySQL Platform Storage](./mysql-platform-storage.md) | MySQL/Alembic、真实执行、服务器迁移与历史保护 | Active |
| [Error Handling](./error-handling.md) | Error boundaries and status handling | Placeholder |
| [Management API Contracts](./management-api-contracts.md) | Executable contracts for management catalogs, environment CRUD, and run environment snapshots | Active |
| [Quality Guidelines](./quality-guidelines.md) | Code quality rules for the new backend and engine integration | Active |
| [Run Execution Contracts](./run-execution-contracts.md) | R01 execution modes, state machine, results, worker lifecycle and migration | Active |
| [API/Web Workbench](./apiweb-workbench-contracts.md) | 接续预检、环境构建、查询包、终端、镜像与真实验收边界 | Active |
| [Context Contracts](./context-contracts.md) | R02 environment/identity/project snapshots, secret references and auth replay | Active |
| [Asset Contracts](./asset-contracts.md) | R03 immutable scenarios/suites, compilation, migration and coverage | Active |
| [Draft Debug](./draft-debug-contracts.md) | 未保存草稿、单步骤前置输入、独立快照与正式证据隔离 | Active |
| [Resource Contracts](./resource-contracts.md) | R04 fixtures, ownership, leases, cleanup and media | Active |
| [Assertion/Wait Contracts](./assertion-wait-contracts.md) | R05 typed business assertions, state polling, bounded retries and traces | Active |
| [Business Database Contracts](./business-database-contracts.md) | 独立业务只读来源、言迹接诊筛选期望与分页核验 | Active |
| [Diagnostic Contracts](./diagnostic-contracts.md) | R06 diagnostics, artifacts, filtered trends, rerun and evidence retention | Active |
| [Scheduling Contracts](./scheduling-contracts.md) | R08 persistent schedules/outbox, CI exits, release evidence and quiet notifications | Active |
| [UI/Evaluation Contracts](./ui-evaluation-contracts.md) | Partial R09/R10 capability boundaries, datasets, budgets and unverified real-world gates | Active |
| [Logging Guidelines](./logging-guidelines.md) | Logging and observability guidance | Placeholder |

---

## Pre-Development Checklist

Before editing backend code for the new architecture, read:

1. [MySQL Platform Storage](./mysql-platform-storage.md) when changing persistence, Mock boundaries or migrations
2. [Directory Structure](./directory-structure.md)
2. [Quality Guidelines](./quality-guidelines.md)
3. [Management API Contracts](./management-api-contracts.md) when a change affects:
   - management pages (`cases / suites / environments / schedules`)
   - environment CRUD
   - run creation with `environment_id`
4. [../guides/cross-layer-thinking-guide.md](../guides/cross-layer-thinking-guide.md) when a change affects:
   - backend API + frontend contract
   - backend run model + engine execution model
   - worker / scheduler / persistence boundaries

Also check these repository docs for onboarding context:

Changes to run/worker/storage/status/Mock boundaries must also read [Run Execution Contracts](./run-execution-contracts.md).

1. `/Users/ys/PyCharmProject/PytestAutoApi/docs/architecture-modernization.md`
2. `/Users/ys/PyCharmProject/PytestAutoApi/docs/getting-started-modernized.md`
3. `/Users/ys/PyCharmProject/PytestAutoApi/platform/backend/README.md`

---

## 部署工具

修改发布流程或部署到154时读取 [标准发布SOP](../../../deploy/SOP.md)。发布工具测试在 tests/deploy，普通脚本仅支持同schema升级；数据库迁移按专项流程执行。

## Current Backend Baseline

### Primary backend application package

Use:

```text
platform/backend/src/pyta_platform_backend/
```

Do **not** introduce a top-level Python package named `platform`, because it conflicts with Python's standard library module.

### Primary execution engine package

Use:

```text
src/testflow_engine/
```

Backend worker code may call into the engine, but keep the boundary explicit:

- backend manages runs, orchestration, worker triggering, and result recording
- engine executes standardized run/case models

### Pydantic compatibility baseline

The modernized project configuration targets **Pydantic v2**, but repository reality may still involve environments that load **Pydantic v1**.

Therefore:

- prefer v2-style code when adding new models
- add compatibility branches when using APIs such as:
  - `model_dump()` vs `dict()`
  - `model_copy()` vs `copy()`
  - `model_fields` vs `__fields__`

Do not assume every runtime environment is already fully upgraded.

---

## Decision Summary

When in doubt, follow these rules:

- New backend functionality goes under `platform/backend/src/pyta_platform_backend/`
- New execution logic goes under `src/testflow_engine/`
- New tests go under `tests/backend/`, `tests/engine/`, or `tests/compat/`
- YAML 兼容回归使用 tests/fixtures；业务测试资产通过平台维护

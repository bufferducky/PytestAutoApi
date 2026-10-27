# testflow_engine 说明

`testflow_engine` 是 PytestAutoApi 的独立执行内核：接收标准运行定义，渲染请求与变量，执行真实 HTTP、断言和清理，产出统一结果。平台负责页面资产、版本、环境、MySQL 持久化与任务编排，worker 调用引擎执行。

日常操作从 [页面工作台](../../platform/README.md) 进入，启动步骤见 [启动指南](../../docs/new-architecture-quickstart.md)。

## 目录职责

| 模块 | 当前职责 |
| --- | --- |
| [models/core.py](models/core.py) | 运行、场景、步骤、请求、断言、上下文与结果模型 |
| [executor/engine.py](executor/engine.py) | 请求步骤、依赖、主流程与清理执行 |
| [executor/rendering.py](executor/rendering.py) | 模板变量与上下文渲染 |
| [executor/transport.py](executor/transport.py) | `TransportAdapter` 与真实 `HttpxTransport`，支持查询参数和不同请求体 |
| [assertions](assertions/) | 通用与业务断言；轮询等待由 [executor/waiting.py](executor/waiting.py) 配合 |
| [plugins](plugins/) | 执行生命周期扩展、身份引导和旧缓存兼容 |
| [reporting/collector.py](reporting/collector.py) | 汇总执行状态、请求和断言，生成统一报告快照 |
| [compat/legacy_yaml.py](compat/legacy_yaml.py) | 将旧 YAML 转换为标准模型并保留迁移信息 |

引擎结果由平台 worker 持久化，并供执行结果页展示。引擎不管理平台 CRUD、数据库迁移或页面状态。`executor/scheduler.py` 中的内存队列仍是独立基础组件；平台实际持久调度由后端 `ScheduleHost` 承担。

## 旧 YAML 兼容

页面保留按内容导入旧 YAML 的入口，转换为草稿后核对请求、断言、依赖，再预检与发布。兼容层与 `LegacyCachePlugin` 独立保留，不依赖已清理的旧脚本框架和业务样例。兼容回归使用合成 fixture；未支持的旧语法需要显式处理，不能把成功解析视为执行等价。

产品新运行显式使用 `transport_mode=live`。引擎的可注入传输用于受控测试和集成，离线测试通过不能替代真实业务验证。

## 验证与阅读

先在仓库根目录按 [pyproject.toml](../../pyproject.toml) 安装开发依赖，再执行：

```bash
source .venv/bin/activate
make test-engine
# 需要检查平台集成时
make test-new
```

建议结合 [引擎测试](../../tests/engine/) 和 [兼容测试](../../tests/compat/) 阅读模型、执行器、传输、断言、插件与报告；平台调用入口见 [workers/run_worker.py](../../platform/backend/src/pyta_platform_backend/workers/run_worker.py)。

浏览器/移动端旅程 runner 和评估编排保留在 [平台后端](../../platform/backend/README.md)，需各自验证依赖、设备和业务条件。新评估执行禁用；这些扩展代码与测试媒体的保留不代表完整业务、真机或模型质量已验收。

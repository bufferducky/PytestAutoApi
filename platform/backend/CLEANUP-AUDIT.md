# 历史冗余清理审查

日期：2026-10-27。用户确认项目以新版页面交互为入口，旧脚本框架及旧示例、报告、截图不再需要；浏览器、移动端旅程和评估能力保留，核心完善后再发展。

## 已清理

| 项目 | 删除依据 |
| --- | --- |
| 根目录 run.py、common/、utils/、test_case/、requirements.txt | 新版后端与引擎没有导入旧框架；当前 Docker 不复制这些目录。旧入口通过命令行启动 pytest / Allure / 旧通知，不服务当前页面。依赖统一由 pyproject.toml 管理。 |
| data/ 旧业务 YAML | 用户不再需要旧示例。原兼容测试已切换到独立合成 fixture，不再依赖真实旧业务账号或接口。 |
| report/、logs/ | 旧 Allure 原始结果、HTML、附件及本地日志。平台数据库与 artifact root 中的运行证据未操作。 |
| Files/ 中 test-media 以外内容 | 旧教程截图、上传样例和 Excel。新版仍引用的测试媒体完整保留。 |
| pytest-auto-api2/、空 output/playwright/ | 空目录，无执行作用。 |
| src/templates/ | 重复的规范 Markdown，大多数与 .trellis/spec 对应文件相同。运行源码、Trellis 脚本与配置未发现读取者，保留 .trellis/spec 作为当前规范。 |
| 后端 scheduler/ 的 LightweightScheduler / ScheduledJob | 未发现任务注册或扫描调用，应用生命周期实际使用 ScheduleHost。同步移除 create_app 的 scheduler 参数、app.state.scheduler 和旧包导出；装配测试改验证实际 ScheduleHost 的轮询周期。 |
| DemoSuiteService / AssetService 的无用依赖 | 演示列表固定为空、执行和导入返回 410，演示服务不再使用执行/仓储依赖，资产服务也不读取演示服务。删除构造注入和未读属性。 |
| docs/architecture.md | 内容仅描述已删除的旧脚本框架；当前架构与启动入口同步更新。 |

旧目录内被 Git 跟踪的 __pycache__ 也随旧框架删除。忽略规则补充 report/logs/output，防止运行产物重新进入版本管理。

## 保留边界

| 项目 | 原因 |
| --- | --- |
| 前端旧 YAML 内容导入、引擎 compat/ 与 LegacyCachePlugin | 页面仍提供粘贴 YAML 导入草稿，使用独立兼容层，不依赖旧 utils。导入本身不执行业务请求。 |
| tests/fixtures/legacy_yaml/ | 新建合成输入验证文件读取、空 is_run、禁用步骤、变量替换、缓存依赖和字段映射；不是产品默认资产。后端导入回归走与页面一致的 yaml_text 入口。 |
| data 路径兼容 API | 保留已有受控路径校验，但仓库不再附带业务 YAML。使用该入口需部署方显式提供 data 文件；日常交互优先使用页面内容导入。 |
| runners/、journey/evaluation 服务、Files/test-media | 按用户要求保留现有未来能力；评估新执行仍禁用，不把保留代码宣称为完整业务验收。 |
| .runtime/、MySQL、artifact root | 本轮是源码与旧资料清理，不清平台数据、历史证据，也不连接业务数据库。 |
| InMemory* 基类、通用序列化、Pydantic 兼容分支 | SQL 仓储仍继承或引用；通用序列化现位于 serialization.py，sqlite_support.py 只保留兼容导出。 |
| 退役 Demo HTTP 路由与 schema | 继续给旧调用者空列表或明确 410。删除旧实现不改变现有 HTTP 退役语义。 |
| docs/reviews/、Trellis、AI 工具配置 | 保留当前开发规范、验收证据和工具能力；历史审查描述的是当时状态。 |

内部服务构造参数已精简，旧 create_app(scheduler=...) 和 app.state.scheduler 已移除；仓库外直接使用这些 Python 接口的调用者需要同步调整。HTTP 协议与持久调度未变。Git 跟踪的删除均可通过版本历史恢复，未清除 Git 历史。

## 验证

- 针对 YAML 兼容、资产服务与应用装配：43 passed。
- Ruff：后端、引擎及改动的 Python 测试通过。
- 前端 build：通过 TypeScript 检查与 Vite 构建。
- 前端 reliability、environment-variables、environment-unsaved 三组脚本通过。
- 完整 Python 回归：284 passed、9 skipped（139.74 秒）；跳过真实 MySQL 与默认关闭的浏览器集成。
- 显式工作台浏览器回归：1 passed（19.11 秒），验证编辑、发布、真实本地 HTTP 运行及离线错误。Chromium 首次被沙箱阻止，获准在沙箱外重跑后通过。
- 未连接业务数据库、未执行真实公司接口、未部署。未配置真实 MySQL 时相关集成测试仍跳过。

## 文档交付说明

用户全局忽略规则包含 `docs/` 和 `.trellis/`。本次需要的启动、架构、资产、资源、MySQL 迁移手册及修改的目录/数据库规范已选择性使用 intent-to-add 纳入 Git 差异，新 fixture 和本审查记录也纳入。全局配置保持不变；具体内容未暂存、未提交。

## 模块名称与归属整理

- `workers/run_worker.py:RunWorker` 为正式运行消费者，替代误导性的 MemoryWorkerRunner 名称；旧 workers.runner 模块重导出类别名与 WorkerExecutionResult。
- JSON/时间编解码实现移动至 `repositories/serialization.py`，旧 sqlite_support 保留重导出；仓储包正式导出 SqlRunRepository、SqlManagementRepository，保留旧 Sqlite 别名。
- 应用内部统一使用 resolve_database_url，旧 resolve_state_db_path 方法保持转发兼容。
- 言迹接入代码移动至 `integrations/yanji/query_pack.py`；两份 JSON 原样移至其 data 包，迁移前后字节/hash 一致。路由与资产研究导入使用新资源包。旧 services.yanji_regression 重导出历史函数。
- 前端正式容器组件使用 ContentPanel，纯输入校验移动至 utils/debugInputs；没有改变模板结构、样式或交互。
- 新增隔离发布目录测试：仅复制 Docker 所需两个源码目录，验证 S01—S16 契约接口、650 条研究观察导入、无新运行及 Python 旧导入兼容。独立发布目录测试通过不等同于完整 Docker 镜像验收。
- 工程发行名、Case/Scenario 模型、测试媒体位置和大服务分层本轮保持。

命名整理后的验证：完整 Python 回归 **285 passed、9 skipped（139.70 秒）**，真实工作台 Chromium 回归 **1 passed（18.30 秒）**；前端构建与类型检查、三组前端脚本、Ruff 和差异空白检查均通过。新增隔离发布布局测试同时验证正式入口、旧导入兼容及迁移后资源读取。未验证真实 MySQL 或完整 Docker 构建，未部署。

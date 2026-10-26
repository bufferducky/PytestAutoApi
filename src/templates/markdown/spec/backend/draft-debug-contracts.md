# 未保存草稿调试契约

## 1. Scope / Trigger

修改草稿调试、资产编译、运行用途、正式统计或发布证据时读取。草稿调试不是自动发布，也不绕过真实执行上下文。

## 2. Signatures

`POST /api/v1/scenarios/debug` → 202 `{run_id,status,dispatch_channel,environment_id,environment_name}`。

`DraftDebugRequest`：draft 对象；可选 asset_id/revision/step_id/environment_id；inputs 与 parameters 对象；build/requested_by；必须 `live_confirmed:true`。额外字段拒绝，客户端不能提交 run_definition、context_snapshots 或 run_purpose。查询/取消复用 `/runs/{id}` 与 `/runs/{id}/cancel`。

## 3. Contracts

- 当前编辑内容经 validate_draft 和现有编译/上下文校验后冻结；不写 asset_drafts/asset_versions。独立快照保存在现有 runs.payload_json.debug_snapshot，运行/outbox 沿用持久事务，无新增表。
- 执行固定 run_purpose=debug、validation_scope=debug、business_scope=draft_debug。移除正式 asset_ref/scenario_refs/scenario_version_ref 及 case.metadata.scenario_ref，不冒用编译临时 version=0。
- 正式 eligible_for_release、live_stats、发布 exit_code 和趋势排除调试；复跑保留原调试用途。覆盖依赖正式 eligible 和版本引用，不接受调试结果。
- 整场景保留 setup/cleanup、资源和预算。单步仅保留选中启用主步骤，不隐式执行前置。缺 outputs（含断言引用和 CUSTOM_RULES.reads）在入队前拒绝，inputs 显式补齐后注入独立 scope。涉及 fixture、清理步骤或带清理的写步骤要求整场景调试。
- inputs/parameters 不接受秘密明文；凭证走身份配置和 secret_ref。后台仍检查契约、同环境、origin 和脱敏边界。单步仍要求场景整体结构可编译，不能靠调试绕过未知迁移契约。

## 4. Validation & Error Matrix

| 输入 | 行为 |
|---|---|
| 缺真实范围确认/额外编译字段 | 422，零任务 |
| 未确认契约/无效场景 | 400，零业务请求 |
| 单步缺前置输出 | 400，missing_inputs 列出路径，零任务 |
| fixture 或清理约束无法满足 | 400，提示整场景 |
| 调试成功 | 可读真实证据，eligible=false，正式统计不变 |
| queued 取消后重启 | 保留取消，不重新执行 |

## 5. Good / Base / Bad Cases

Good：修改未保存断言立即调试，结果使用修改内容，草稿和发布版本保持原样。
Base：未保存资产无 ID 也能调试；后续编辑不改变已执行快照。
Bad：隐式发布调试版本；只在 UI 隐藏调试但 SQL 仍计入正式统计；缺变量自动执行前置写请求。

## 6. Tests Required

`tests/backend/test_draft_debug.py`：本地真实 HTTP、未保存快照、不发布、统计隔离、正式发布兼容、普通/自定义断言前置输入、单步仅一个请求、完整清理、取消/重启、客户端额外字段拒绝。

`tests/backend/test_platform_frontend_browser.py`：真实表单未保存调试、取消离开保留编辑、正式发布、变量类型、关联调度与九宽度布局。MySQL 集成未启用时明确记录，不能把 SQLite 证明写成生产 MySQL 验收。

## 7. Wrong vs Correct

Wrong：`publish(draft); run(latest)` 用于调试，污染正式资产与证据。

Correct：`validate_draft → _plan(独立快照) → _create_prepared(run_purpose=debug)`，不产生发布引用，统一执行链完成后按用途隔离证据。

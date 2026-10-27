# API/Web 工作台接续契约

## 1. Scope / Trigger

修改预检、资产运行范围、声明编译、言迹查询接入、Web 登录、部署资料或默认测试入口时适用。当前 MySQL/live-only/新评估禁用政策继续有效。

## 2. Signatures

- `ContextTransport.preflight()`：configuration/authentication/context/service；必需归属两维均回读才 context=passed。
- `TargetProfile.request_headers: dict[str,str]`：登录/查询共用公开默认头，禁止覆盖认证/Host/Dept-Id/Tenant-Id。
- `AssetService.plan/run(... AssetRunRequest)`：从 target 快照派生单环境，校验显式环境，保存环境公开快照及 build。
- `GET /api/v1/runs?environment_id=&target_id=&build=`：按固定证据筛选。
- `POST /api/v1/imports/yanji-query`：target_ref/identity_ref/binding_ref/expected_user_id，创建幂等查询草稿。
- `POST /api/v1/journeys/import-yanji-query`：上述引用加 chromium_version，创建 Web 登录/查询旅程。
- `GET /api/v1/regression-packs/yanji`、`GET /api/v1/runner-capabilities`。
- `POST /api/v1/imports/legacy`：target_ref、yaml_text（<=1MiB）或兼容 path。

## 3. Contracts

- 缺归属证据是 not_verified，错误归属 failed，无需上下文 not_required；checks 非空不证明归属。
- 套件混合环境当前拒绝；资产默认入口即使未传 environment_id，也不得丢环境。build 缺省仍 unspecified，不能据此放行业务发布。
- 逐步骤 plugin_refs 没有消费者，当前明确拒绝所有非空声明。worker 按运行类型装配插件与逐步骤选择不是同一契约。
- 言迹 API 查询包仅允许 https://api-test.yanjiai.com；Web 包仅允许 https://web-test.yanjiai.com。创建不自动登录/发布/执行或解除完整 S/W 风险。
- 同账号 PC token 会互踢；API 与 Web 回读的登录/查询终端头必须一致，并使用可共存的明确终端策略。浏览器登录仍为真实 PC 行为，不伪造 UI 会话。
- Web 支持精确 placeholder 作为既有页面无 label/testid 的补充，拒绝 CSS/XPath/坐标。秘密值只在内存解析，带 value_ref 的旅程失败不直接采图，原生含凭证 trace 继续拒绝。
- business_scope 单独区分 yanji_query/yanji_web/unclassified/historical_demo；validation_scope=live 只说明真实传输。eligible_for_release 是旧字段的执行证据投影，业务发布仍看固定构建的 strict 报告。
- 脱敏研究元数据和 S01—S16 来源指纹随 Python 包交付；不复制原始前端包/客户响应/密码。默认 pytest 跑 tests/；旧脚本框架与业务 test_case/ 已退役，合成兼容输入存 tests/fixtures。
- 镜像 INSTALL_WEB_RUNNER=1 安装 Chromium，PLAYWRIGHT_BROWSERS_PATH=/opt/pyta-browsers 供非 root worker 使用；API-only 缺能力明确显示。版本以实际安装/运行基线为准。

## 4. Validation & Error Matrix

| 输入/条件 | 结果 |
|---|---|
| 仅 code 查询/只验证一维 | context not_verified |
| 错租户/项目 | context failed |
| 两维准确回读 | context passed |
| 不需要归属 | context not_required |
| 错显式环境/混合环境 | 400，零新 run |
| 不支持的逐步骤插件 | 发布/预检拒绝，不丢弃 |
| 非测试目标导入言迹包 | 400，零业务请求 |
| 缺秘密引用 | 配置失败，不用旧密码 |
| 旧 YAML 解析失败 | 400，错误不回显上传内容 |
| 研究 bundle 缺失 | 503，可读原因 |
| 驱动包存在而 Chromium 缺失 | available=false，报告原因 |

## 5. Good / Base / Bad Cases

Good：默认页面提交后可按环境/目标/构建查回；测试查询包发布后执行 4 场景，最终 Linux Web 查询 8 步；结果只说明该查询范围。
Base：只做配置预检不登录；API-only 镜像能运行 API，Web 明确不可用；未核实部署版本保留 unspecified。
Bad：code=200 当项目通过；用套件首目标掩盖多环境；把查询 smoke 或源码指纹当 16 项风险全通过；用 PC 互踢后的自动重试隐藏身份串用。

## 6. Tests Required

- test_context_profiles：缺/单维/错/正确归属、not_required、终端头在登录/查询一致、默认头不能覆盖作用域。
- test_scenario_assets：默认场景/套件入口环境/构建与公开筛选、混合环境零新run、插件显式拒绝、查询包幂等/仅草稿/测试环境约束、YAML 内容导入和错误无秘密。
- test_journey_runners：秘密填写后的失败不采图；S 契约源状态不能伪装 live。
- test_platform_frontend_browser：真实表单→发布→live→结果→断网；非空运行数据下六路由/九宽度无全页横向溢出。
- 隔离 MySQL、实际 Chromium、干净镜像与言迹测试 API/Web 分开留证；默认跳过不能当真实检查通过。

## 7. Wrong vs Correct

```python
# Wrong: 可达/已登录推断当前项目正确
context_status = 'passed' if target['checks'] else 'not_verified'

# Correct: 两维都有真实回读证据；维度可来自多个已确认查询
context_status = 'passed' if verified == {'tenant_id', 'project_id'} else 'not_verified'
```

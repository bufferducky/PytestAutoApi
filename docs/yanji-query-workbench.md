# 言迹测试环境 API/Web 查询接入

本轮提供可运行的查询 smoke、平台可信度修复和部署输入；不是 S01—S16/W01—W04 全部验收通过。仅使用 `api-test.yanjiai.com` 与 `web-test.yanjiai.com`，没有调用言迹生产站点或修改其业务源码。

## 已实现的操作

1. 环境页保存测试环境、目标、身份秘密引用和项目绑定。目标可编辑 JSON/form、密码转换、token 路径、终端 User-Agent 及归属查询。
2. API 目标的归属查询使用 `/api/v1/user/role_info`，租户字段 `data.tenantId`、项目字段 `data.deptId`；真实预检须同时回读这两个维度。只校验业务码不能得到 context passed。
3. 场景页选择测试目标/身份/绑定和明确的预期用户 ID，展开“接入言迹测试环境查询包”，创建四条查询草稿。不会自动发布、运行或覆盖已编辑资产。
4. 保存→预检→发布→选择构建和环境→运行。结果页可按环境/目标/构建筛选，显示业务范围；草稿未保存时不能预检/发布。请求头、查询参数、请求体类型可用表单编辑。
5. Web 旅程面板选择 Web 测试目标/身份/项目，自动回填已安装 Chromium 版本，创建测试 Web 查询 smoke，然后预检和运行。包含登录、菜单可见性、用户指定的接诊入口与 API 身份/项目回读；不绑定 W 风险编号，避免部分验证解除完整风险。

查询 smoke 的断言覆盖用户 ID、当前租户/项目、菜单数组、接诊分页总数/行结构和人设分页结构。空列表与分页结构通过不表示写入、业务结果或权限负向通过。

## 终端与秘密配置

言迹源码按 User-Agent 区分终端；同账号 PC 登录会互踢，APP 会话可共存。API 与 Web 回读目标需要明确使用合适的移动终端 User-Agent，保持登录和查询一致；浏览器仍执行真实 PC 登录，不能靠重试掩盖互踢。

建议使用独立自动化账号。Compose 支持以下服务端秘密引用，只在部署环境的受限配置中填写值：

- `PYTA_SECRET_YANJI_TEST_USER`、`PYTA_SECRET_YANJI_TEST_PASSWORD_DIGEST`：API 查询目标；如密码引用保存摘要，目标转换为 none。
- `PYTA_SECRET_YANJI_WEB_USER`、`PYTA_SECRET_YANJI_WEB_PASSWORD`：Web 输入原始密码引用；供 API 回读的同目标登录转换为 md5。

不要把值写入代码、草稿、导出或文档。空引用使预检明确失败，不回退旧密码。默认请求头禁止覆盖 Authorization、Host、Dept-Id、Tenant-Id。

Web 登录字段仅有 placeholder 时支持精确 placeholder 定位；仍拒绝坐标/CSS/XPath。带秘密引用的失败页面不直接采图；不启用带凭证的原生 trace/录屏，保留脱敏步骤结果与错误。

## 交付与测试入口

- 默认 `.venv/bin/python -m pytest` 运行 `tests/` 离线检查；旧 `test_case/` 不默认执行。
- MySQL 专项需要 `PYTA_TEST_MYSQL_URL` 且数据库名称以 `pyta_validation` 开头。
- 真实浏览器专项需要 `PYTA_RUN_BROWSER_TESTS=1` 和安装的 Chromium。驱动、浏览器、精确版本不就绪时明确阻塞。
- `INSTALL_WEB_RUNNER=1` 构建可选 Chromium 镜像，Compose 默认启用；API-only 镜像可设置为 0。浏览器位于非 root worker 可读的 `/opt/pyta-browsers`，API 会报告实际版本。
- 研究导入从包内 `testflow_engine/business_data/yanji-research.json` 读取脱敏路径/字段清单，不再依赖源码树的 docs 目录。完整原始脚本与客户响应没有打入镜像。
- 旧 YAML 可直接粘贴上传，限制 1 MiB；导入保留迁移缺口并移除旧秘密。媒体仍按受控媒体资源契约使用明确挂载或上传来源，不把未提供媒体伪装成可运行。
- `/api/v1/regression-packs/yanji` 提供 S01—S16 来源文件指纹、资源要求及验收映射；source_observed 不是 live_verified。

## 本轮实际证据与限制

2026-10-26，指定测试账号在独立本地 MySQL 中创建并发布四场景套件，经现有 worker 访问真实 API 测试服务，4 场景/12 断言通过。独立 Chromium 148.0.7778.96 执行测试 Web 登录与查询，10 步/6 断言通过，最后由 API 回读同一用户/项目。未修改现存接诊、录音、配置或人设关联。

API 部署构建未确认，保留 unspecified；Web 记录实际入口 HTML 的 SHA-256，仅代表该入口产物指纹，不证明 API 代码与本地 dev 一致。严格发布摘要继续列出未验证风险。

指定账号仅关联一个项目，且 isOpsUser=false。项目切换、低权限服务端拒绝、中台下发、非目标项目不变、专属录音/人设写入与恢复、专属接诊详情/分析结果等完整验收仍缺明确资源。测试环境已有其他测试记录，不因名称含“测试”就擅自修改。当前交付保持“部分实现、真实查询已验证”，不标全量完成。

Android 真机和 AI 质量后续处理，新评估执行仍禁用。2026-10-26 用户授权后已部署服务器，沿用原 MySQL/附件并保留备份和旧镜像；部署详情见 deploy/README.md。不能把新平台切回旧 SQLite 当作无损回滚。


## Web 入口差异复盘

Linux Chromium 156 首次联调在“全部”菜单动作失败，保留原 run。源码 SidebarNav.vue 的接诊三级菜单受 roleType===1 控制；角色尚未加载时点击接诊记录已直接进入 visitor-register，之后不能再无条件点击三级“全部”。查询 smoke 使用用户明确给定的 `/visitor-register?roleId=&routerId=0` 入口，保留可见菜单、查询入口和 API 归属断言；该 smoke 的 8 步不代替完整角色菜单/项目切换验收。不存在自动重试点击或把失败记录改绿。

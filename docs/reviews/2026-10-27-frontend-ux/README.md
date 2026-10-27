# 前端全量体验优化验收

2026-10-27，本地完成八类页面的 Element Plus 迁移与工作流重排。组件库实际安装版本为 **2.14.7**；保留 Vue 3、TypeScript、Pinia、Vue Router 和原有后端契约。

## 改变后的操作方式

- 用例页左侧选择场景/步骤，只编辑当前步骤；请求参数、头、体、断言、提取、高级设置直接切换。保存检查全部模型并定位隐藏错误，调试结果在当前工作区显示。
- 编辑、场景/套件设置、发布版本、正式运行分别进入；保存与调试在工作区工具栏，版本和正式运行不再排在所有步骤之后。
- 套件、环境和调度各保留一个主目录。环境/目标/身份/绑定有独立入口；结果页使用可筛选列表和就近详情，避免环境名逐字竖排及状态裁切。
- 扩展工具使用四类导航，资源与旅程工具内进一步按任务分区。手册搜索与控件统一，正文限制阅读宽度；原文章、小节和问号新标签页保留。
- 公共输入、可检索下拉、多选、按钮、表格、标签、分页、空态、结果摘要和确认对话框使用库组件。异步确认前冻结草稿、环境、构建和参数，取消不会写请求。

## 验证结果

| 检查 | 当前结果 / 证据 |
| --- | --- |
| 生产构建及 TypeScript | 通过，见 [构建日志](./build.log) |
| 前端可靠性 | 通过；包括异步确认快照、取消不发送、旧响应保护及原业务断言 |
| 手册内容 | 通过；44 篇、161 个主题、23 幅图，稳定锚点、链接及真实搜索有效 |
| 真实浏览器 | `1 passed in 53.76s`，见 [浏览器日志](./browser.log) |
| 桌面布局 | 1280/1440/1920px，八路由默认/展开 48 次 + 实际打开的业务/请求/工具标签 108 次，共 **156 次** |
| 页面脚本错误 | **0** |
| 业务链路 | 创建、未保存调试、保存、预检、发布、场景正式运行、套件计划/运行、失败诊断通过 |
| 编辑稳定性 | 三份各三步场景，检索/切步/复制/移动/删除、隐藏 JSON 错误定位、类型/请求头/metadata 往返通过 |
| 环境及调度 | 类型变量、目标/身份/项目绑定创建、多选及秘密引用、取消切分类、时间预览、暂停计划保存、确认取消/Escape 不变更通过 |
| 扩展工具 | 四类工具可操作，真实保存只读资源定义，保留历史评估禁用约束 |
| 帮助与手册 | 悬停/键盘/不冒泡/边界、新标签页及未保存输入保护、逐篇阅读、23 个实际 SVG 通过 |
| 差异格式 | `git diff --check` 通过 |

机器结果见 [verification.json](./verification.json)。所有业务执行只指向隔离本地 API/SQLite 与本地 `/check`，未调用公司接口。

## 页面迁移清单

| 页面 | 实际组件与主要变化 | 截图 |
| --- | --- | --- |
| 工作台 | ElButton、共享 ElTag、导航/面包屑；真实最近资产和失败直达 | [1440px](./1440-dashboard-default.png) |
| 用例 | ScenarioAssetsPanel 内 ElTabs/Input/Select/Button/Empty/Table/Alert；步骤目录、请求分区、发布/运行及快照调试 | [多步骤](./1440-workspace-multistep.png)、[1280px](./1280-cases-default.png) |
| 套件 | 共享资产工作区，固定版本检索、排序、预检、发布与运行 | [1440px](./1440-suites-default.png) |
| 环境 | ElTabs/Table/Tag、可检索 Input/Select；四类目录、类型变量与保护 | [1440px](./1440-environments-default.png)、[高级绑定](./1280-environments-last-tab.png) |
| 结果 | ElTable/Pagination/Tabs、Select/Input；常用筛选、当前页查找、并排详情与证据标签 | [1280px](./1280-runs-default.png)、[1440px](./1440-runs-default.png) |
| 调度 | SchedulePlansPanel 内 Tabs/Input/Select/Button/Empty；计划目录、编辑/记录/运维分区 | [1440px](./1440-schedules-default.png)、[运维](./1280-schedules-last-tab.png) |
| 扩展 | ElTabs/Alert，四类业务面板内统一控件，资源和旅程二级任务分区 | [1440px](./1440-extensions-default.png) |
| 手册 | ElInput/Button、公共导航；保留目录、搜索、深链接及真实 Mermaid，限制正文宽度 | [1440px](./1440-manual-default.png)、[1920px](./1920-manual-default.png) |

1440px 八类页面、1280px 用例/结果与高级入口、1920px 手册等代表截图已人工查看；修正了问号被公共按钮样式覆盖、帮助浮层并存、状态标签入场截图、环境目录列宽和配置目录空白拉伸等问题。截图禁用动画以记录稳定状态，实际交互另由浏览器操作验证。

## 逐项验收映射

验收定义见 [PRD](../../../.trellis/tasks/10-27-frontend-ux-component-library/prd.md)，原始问题见 [20 项清单](../../../.trellis/tasks/10-27-frontend-ux-component-library/ux-audit.md)。

| 条款 | 完成证据 |
| --- | --- |
| AC01 | package.json、lockfile、main.ts、App.vue 及上表八页真实控件/截图；2.14.7 已安装锁定 |
| AC02 | 156 次布局检查、三宽度截图及人工审查；调度保存按钮/帮助中心线新增实际几何断言 |
| AC03 | ux_workspace.three_assets_three_steps、search_and_single_visible_step、primary_actions_first_viewport；多步骤截图 |
| AC04 | hidden_invalid_json_located、switch_copy_move_delete_preserve_inputs、typed_body_headers_and_extensions_roundtrip；保留 raw/form 序列化可靠性断言 |
| AC05 | created_published_run、正式计划预览、发布与版本/正式运行标签实际打开；截图及 API 固定版本断言 |
| AC06 | 首页失败记录不被后续成功挤掉，点击直达失败诊断；真实最近资产、显式空态及离线错误 |
| AC07 | 套件保存发布、固定引用核验可靠性、published_suite_plan_and_live_run，本地真实 HTTP 成功及 build 断言 |
| AC08 | typed_environment_variables、target_identity_binding_created、multiple_select_secret_refs_preserved、cancel_category_change_preserves_input |
| AC09 | 列表/详情截图，环境/状态及全部筛选标签检查，真实失败断言差异、复制脱敏摘要入口；API 原筛选/趋势/资源/重跑函数保留 |
| AC10 | schedule_select_preview_reset、schedule_confirm_cancel_escape_no_mutation、三类调度标签与预览5次；代码保留暂停/启用/删除/记录/全局运维契约 |
| AC11 | all_four_tools_operable、readonly_resource_definition_saved、new_evaluation_remains_disabled；三宽度逐个打开资源/旅程子分区 |
| AC12 | manual 全量正文/图形/深链接结果、help_hover_keyboard_desktop、help_does_not_mutate_forms、新标签页保留输入 |
| AC13 | 隐藏 JSON 及依赖错误定位、真实 MessageBox 取消和 Escape、库下拉/多选、帮助焦点与关闭；离线显式错误 |
| AC14 | unsaved_draft_debug、formal_run_preserves_unsaved_on_cancel、invalid_dependency_prevents_debug_request；可靠性中的迟到响应、重复提交、异步确认冻结/取消和保存中输入断言 |
| AC15 | 构建/类型、可靠性、手册、完整浏览器链路、156 次布局与零脚本错误；未通过项未省略 |
| AC16 | 本报告、日志、JSON、截图、README、当前入口手册和工作台规范更新；Trellis 记录以不自动提交方式保存 |

## 命令

```sh
npm run build --prefix platform/frontend
node tests/frontend/reliability.cjs
node tests/frontend/manual-content.mjs
PYTA_RUN_BROWSER_TESTS=1 PYTA_BROWSER_EVIDENCE_DIR=docs/reviews/2026-10-27-frontend-ux .venv/bin/python -m pytest tests/backend/test_platform_frontend_browser.py -q -s
git diff --check
```

新增实际交互位于 `tests/backend/frontend_ux_browser_support.py`，复用原浏览器隔离 API；旧业务断言已保留并适配真实库下拉、标签页和确认。没有通过删除断言、更换演示数据或伪造接口结果获得通过。

## 边界与限制

- 本地实现和验收完成，未部署远端、未提交代码；原有未提交业务/手册变更保留。
- 后续不做手机专项；公司业务、真实登录秘密、Web/真机执行和公司定时任务未在本次验收中执行，原能力及阻塞约束保留。
- 运行关键词仅查当前页，服务端筛选契约保持；刷新/关闭前的浏览器原生离开提示继续保留。
- 构建仍提示已有 Mermaid/布局引擎等部分 chunk 较大；页面按路由延迟加载，库组件显式注册。此提示不是构建失败，也不宣称已完成专门性能基准测试。

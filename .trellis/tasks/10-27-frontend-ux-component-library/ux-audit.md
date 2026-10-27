# 全量前端体验问题清单

核查日期：2026-10-27。依据为当前源码、依赖、规范、历史记录及后来补充的 [当前真实浏览器基线](./research/baseline/README.md)。基线覆盖八页布局，已人工查看其中用例、结果、环境截图；不把自动布局通过等同于全部体验合格。用户确认全部类别均严重影响体验，本表全部纳入任务，不转为可选后续项。

“关键路径/全局一致性”用于安排先后，不代表后者可省略。验收条款以 [PRD](./prd.md) 为权威。

| ID | 严重性 / 问题 | 当前代码证据 | 用户影响与改进方向 | 验收 |
| --- | --- | --- | --- | --- |
| UX01 | 全局一致性：无成熟 UI 组件体系 | `platform/frontend/package.json:12`；`platform/frontend/src/main.ts:1`；`platform/frontend/src/styles/base.css:54` | 原生控件通过 CSS 整理外观，校验、选择器、弹窗、分页和反馈仍各自实现；采用 Element Plus，覆盖全部页面实际交互 | AC01、AC02、AC13 |
| UX02 | 全局一致性：样式职责过宽 | `platform/frontend/src/styles/base.css:1`；`platform/frontend/src/components/ScenarioAssetsPanel.vue:537`；`platform/frontend/src/pages/RunsPage.vue:1087` | 全局规则与页面覆盖叠加；统一 token 和公共组件，收窄旧原生选择器 | AC01、AC02 |
| UX03 | 关键路径：编辑、发布、运行同页堆叠 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:23`、`:138`、`:144` | 需要穿过其他步骤找预检、发布和运行；按任务分区，主要操作固定可达 | AC03、AC05 |
| UX04 | 关键路径：步骤导航只负责滚动，全部表单连续铺开 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:65`、`:67`、`:261` | 多步骤场景不断变长；固定目录，只编辑当前步骤，模型保持 | AC03、AC04 |
| UX05 | 关键路径：高频请求配置藏在请求选项中 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:87`、`:91`、`:92`、`:93` | 请求头、参数和体与高级策略混排；使用直接可达的具名分区 | AC04 |
| UX06 | 关键路径：技术字段与请求争抢注意力 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:76`、`:85`、`:108` | 稳定 ID、阶段、契约确认和扩展增加认知负担；保留约束，移到明确高级区，执行前展示必要确认 | AC04、AC05、AC14 |
| UX07 | 关键路径：调试是插入的大表单，结果远离编辑上下文 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:66`；`platform/frontend/src/components/ScenarioDebugPanel.vue:5`、`:18` | 编辑、执行范围与证据之间上下查找；建立就近结果区，区分请求/响应/断言/变量并突出失败 | AC03、AC14 |
| UX08 | 全局一致性：部分业务反馈直接展示原始对象 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:143`；`platform/frontend/src/components/ContextProfilesPanel.vue:76`；`platform/frontend/src/pages/RunsPage.vue:33`、`:145`；`platform/frontend/src/components/SchedulePlansPanel.vue:31` | 用户需要自己读 JSON；先给结论、问题、范围和下一步，原始记录仍保留 | AC09、AC10、AC13 |
| UX09 | 关键路径：浏览器确认框承担复杂范围核对 | `platform/frontend/src/components/ScenarioDebugPanel.vue:94`；`platform/frontend/src/components/SchedulePlansPanel.vue:131`、`:135`、`:146`；`platform/frontend/src/pages/EnvironmentsPage.vue:370` | 长文本难读且割裂；用库对话框展示对象、环境和范围，保留取消和焦点行为 | AC10、AC13、AC14 |
| UX10 | 关键路径：关键目录不可检索 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:48`、`:148`；`platform/frontend/src/components/SchedulePlansPanel.vue:9`；`platform/frontend/src/components/ContextProfilesPanel.vue:47` | 条目增多后难找；名称和必要 ID 检索，空态/失败明确，不静默替换固定引用 | AC07、AC08、AC10 |
| UX11 | 全局一致性：主目录之外另有折叠概览 | `platform/frontend/src/pages/CasesPage.vue:3`、`:6`；`platform/frontend/src/pages/SuitesPage.vue:3`、`:4`；`platform/frontend/src/pages/SchedulesPage.vue:3`、`:4` | 同对象多个入口缺乏联动；每页一个主目录，必要统计归入当前上下文 | AC06、AC07、AC10 |
| UX12 | 关键路径：目标、身份和绑定入口隐藏 | `platform/frontend/src/pages/EnvironmentsPage.vue:3`；`platform/frontend/src/components/ContextProfilesPanel.vue:7` | 先找折叠再切配置类型；改为明确标签，保留登录/归属预检和公开高级配置 | AC08 |
| UX13 | 关键路径：运行列表和详情上下堆叠，表格文字挤压 | `platform/frontend/src/pages/RunsPage.vue:5`、`:101`、`:717`、`:1095`；当前 `research/baseline/1440-runs-default.png` | 实际截图中环境名逐字竖排、右侧状态被局部裁切，选记录后还需滚动找详情；合理分配关键列宽、元信息进入详情、列表与详情就近，失败和步骤证据优先。不能用无整页溢出代替可读性 | AC02、AC09、AC15 |
| UX14 | 关键路径：所有运行筛选收进同一折叠表单 | `platform/frontend/src/pages/RunsPage.vue:15`、`:16`、`:29` | 常用/少用条件无层次；常用条件常显，更多条件一次进入，分页与趋势职责清楚 | AC09 |
| UX15 | 关键路径：调度编辑、目录、记录和运维混排 | `platform/frontend/src/components/SchedulePlansPanel.vue:7`、`:31`、`:32`、`:34` | 建计划与查任务不聚焦，单计划与全局操作易混；目录主导，编辑/记录/运维分区 | AC10 |
| UX16 | 全局一致性：扩展工具靠连续折叠发现 | `platform/frontend/src/pages/ExtensionsPage.vue:4` | 不易理解能力与当前上下文；具名工具目录、用途说明和内容区，保留全部能力 | AC11 |
| UX17 | 全局一致性：工作台与手册需同步迁移 | `platform/frontend/src/pages/DashboardPage.vue:3`、`:10`；`platform/frontend/src/pages/ManualPage.vue:5`、`:12` | 既有快捷入口和完整手册是优点；统一控件和密度，维护真实数据、正文及定位。这是覆盖要求，不捏造手册缺失/搜索失效 | AC06、AC12 |
| UX18 | 关键路径：校验依赖原生表单和滚动定位 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:23`、`:239`、`:446`、`:460` | 单步骤标签页下旧 invalid/details 不足；完整模型校验定位具体步骤/分区/字段，不能丢校验 | AC04、AC13 |
| UX19 | 关键路径：已有未保存/异步保护不能退化 | `platform/frontend/src/components/ScenarioAssetsPanel.vue:288`、`:332`；`platform/frontend/src/components/ScenarioDebugPanel.vue:50`、`:85`；`platform/frontend/src/components/SchedulePlansPanel.vue:59` | 异步确认产生新等待窗口；防取消后执行、迟到确认作用新对象、切标签丢编辑和旧响应覆盖 | AC13、AC14 |
| UX20 | 全局一致性：旧通过记录不足以证明本轮完成 | `tests/frontend/reliability.cjs:12`；`tests/backend/test_platform_frontend_browser.py:22`；`docs/reviews/2026-10-26-workbench-ui/verification.md:3` | 测试依赖旧 DOM，截图早于当前修改；保留业务断言，适配库交互，增加全页面路径和人工截图审查 | AC15、AC16 |

## 用户五类问题的覆盖

| 用户问题 | 清单范围 |
| --- | --- |
| 观感、排版 | UX01、UX02、UX11、UX13、UX17 |
| 找功能 | UX05、UX10、UX12、UX14、UX16 |
| 操作多、反复滚动 | UX03、UX04、UX09、UX11、UX15 |
| 写接口、调试看结果 | UX04—UX08、UX13、UX18、UX19 |
| 缺组件库与一致交互 | UX01、UX02、UX08—UX10、UX17、UX20 |

## 证据边界

- 已人工查看 2026-10-26 用例/运行/环境和 2026-10-27 手册历史截图，仅作对照；源码已移除的旧大标题与常量卡不列当前缺陷。
- 本次补充实际运行基线及八页×三桌面宽度的默认/展开截图。用例、结果、环境三页已人工检查，运行列表的逐字竖排和状态裁切是当前直接视觉证据；其余截图仍需在实施后逐页人工审查。
- 本清单区分可确认的结构问题、覆盖要求与迁移风险，不把可能性当作已复现的业务故障。
- 实施后在独立 review 目录保存真实截图、操作记录并逐条关闭；未验证维持未完成。

## 关闭记录

UX01—UX20 已按本任务范围完成实现与本地验证，验收映射见 [最终报告](../../../docs/reviews/2026-10-27-frontend-ux/README.md)。共 156 次桌面布局检查，包含真实打开的新标签页；业务链路、编辑稳定性、配置与工具及全量手册验证通过。历史原生控件基线仅作对照，完成结论使用本轮真实证据。远端部署与公司业务/真机运行不在本次范围。

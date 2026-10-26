# 个人接口自动化工作台优化分析

状态：用户于2026-10-27批准实施，代码与本地验收已完成，尚未部署。原分析日期2026-10-26。

## 已确认的产品方向

- 优先服务个人高频接口自动化测试，不以 API、Web、App 综合平台为核心。
- 草稿允许直接调试；保存并发布不可变版本后用于正式回归和调度。

## 现状证据

以下路径相对仓库根目录。结论来自源码检查，尚未完成本轮浏览器体验验证。

- `platform/frontend/src/pages/CasesPage.vue:1`：用例页聚合资产编辑、目录概览、覆盖账本、资源、旅程与历史评估。
- `platform/frontend/src/components/ScenarioAssetsPanel.vue:197`：切换草稿有未保存确认，当前组件没有路由离开或窗口关闭保护。
- `platform/frontend/src/components/ScenarioAssetsPanel.vue:290`：预检结果以 JSON 展示；运行依赖已发布版本。
- `platform/frontend/src/components/SchedulePlansPanel.vue:3`：新建只重置选中项和名称，其他字段可能沿用先前编辑值。
- `platform/frontend/src/components/SchedulePlansPanel.vue:7`：套件、版本和环境需要手填 ID 或数字。
- `platform/frontend/src/pages/RunsPage.vue:34`：筛选依赖内部 ID 和 ISO 时间输入。
- `platform/frontend/src/pages/RunsPage.vue:800`：有活动任务时每秒刷新列表。
- `platform/frontend/src/pages/EnvironmentsPage.vue:116`：缺少环境变量编辑器，产品文案包含 patch 实现细节。
- `platform/backend/src/pyta_platform_backend/api/routes/assets.py:71`：已有固定发布版本运行入口，未见草稿专用调试入口。

## 建议范围（待最终评审）

1. 紧凑的列表、编辑和结果工作区，统一间距、状态、操作反馈与有用途的动效。
2. 草稿调试闭环：编辑当前请求、校验配置、真实执行、查看响应、断言和变量。
3. 正式运行保留发布版本与环境快照；调试记录明确标识，不冒充正式回归或发布证据。
4. 环境、套件和版本选择器，常用时间规则，结构化预检和错误定位。
5. 草稿离开保护、表单完整重置、同页数据同步、刷新失败保留旧数据。
6. Web/App 和历史评估等移出高频主路径，保留数据与独立入口。

## 补充确认

- 用户已允许调试尚未保存的编辑内容；执行冻结本次快照，不自动覆盖已保存草稿。

## 技术核实与边界

- 草稿调试需要后端配合，不能仅增加前端按钮或以自动发布版本代替。
- 调试应复用真实执行器和现有上下文、写入范围、契约检查，不能把未发布等同于绕过执行约束。
- 单步骤依赖、调试证据存储和统计隔离需要在设计阶段继续核实；尚未承诺具体接口。
- 完整建议见工作区 `.trellis/tasks/10-26-pyta-api-workbench-ux/` 的 prd.md、design.md 和 implement.md；实施已完成；验收见 docs/reviews/2026-10-27-workbench/verification.json，未部署。

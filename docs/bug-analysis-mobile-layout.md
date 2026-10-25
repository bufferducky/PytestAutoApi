## Bug Analysis: 手机访问时标题逐字换行、侧栏异常拉长

### 1. Root Cause Category

- **Category**: E - Implicit Assumption；次因 D - Test Coverage Gap、A - Missing Spec。
- **Specific Cause**: 默认假设 960px 以上有足够桌面内容空间。
  固定 18.5rem 侧栏和 `minmax(0,1fr) auto` hero 组合，使元信息按固有宽度
  抢光标题空间。标题撑高内容页后，侧栏隐式 Grid 行继续分摊高度，放大视觉异常。
- 手机截图与 980px 浏览器视口复现一致，不能据此断言该手机一定开启了桌面模式。
  viewport meta 已存在，根因不在 Cloudflare 或网络转发。

初始假设：布局挤压 65%、桌面视口触发 25%、旧资源缓存 10%。
真实 DOM 测量：980px 下标题宽度 0px，hero 高 2225.75px，品牌区高 984.04px。
该证据直接支持布局根因，修复后同条件恢复正常，定位置信度超过 90%。

### 2. Why Fixes Failed (if applicable)

1. 首次上线验证了构建、HTTP、API、mock 执行和持久化，没有检查实际手机布局；
   构建和接口成功被误当成页面验收充分。
2. 首轮布局修改解决了截图问题，但 54 组浏览器检查暴露出资源表格、
   调度表格、原生 select、长标签与原始证据的固有宽度溢出。
   因此继续从父容器最小宽度和局部滚动边界修复，而非隐藏全页溢出。

### 3. Prevention Mechanisms

| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | Architecture | hero 可换行、侧栏显式行高、Grid/Flex 子项可收缩 | DONE |
| P0 | Test Coverage | 六路由 × 九宽度的真实 DOM 宽度与高度检查 | DONE |
| P1 | Architecture | 宽表格局部滚动、原始证据局部滚动、长标签换行 | DONE |
| P1 | Documentation | 添加本仓库前端规范及同步模板 | DONE |
| P1 | Code Review | 发布前检查生产构建产物、手机和断点两侧截图 | DONE |

### 4. Systematic Expansion

- **Similar Issues**: 执行结果 hero；运行详情/诊断表格；资源池表格；调度计划表格；
  场景编辑 fieldset；评估长标签与 select。已在同轮布局回归中覆盖。
- **Design Improvement**: 让宽内容在组件内部滚动，让父容器始终可收缩；
  用剩余空间承载留白，而不是把导航项目拉伸。
- **Process Improvement**: 页面发布必须区分构建、接口、真实渲染三种证据；
  初次部署与布局修改都要检查 980px 及断点两侧。

### 5. Knowledge Capture

- [x] `.trellis/spec/frontend/index.md`
- [x] `.trellis/spec/frontend/responsive-layout.md`
- [x] `src/templates/markdown/spec/frontend/` 同步副本
- [x] `tests/frontend/responsive-layout.mjs` 可复用测量与断言

边界：此次验证为桌面浏览器的响应式视口模拟；未直接控制用户的实体手机。

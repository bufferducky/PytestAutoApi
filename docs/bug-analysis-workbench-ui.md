## Bug Analysis: 前端功能堆叠导致工作台难用

### 1. Root Cause Category
- **Category**: A - Missing Spec；同时涉及 C - Change Propagation Failure、D - Test Coverage Gap。
- **Specific Cause**: 已有响应式规范约束了几何溢出，但没有约束公共控件、首屏层级和编辑状态。ScenarioAssetsPanel 把基础字段、请求参数、断言扩展、迁移、发布、运行直接铺开；AppHeader 重复显示常量卡；SuitesPage/SchedulesPage 保留“后续扩展点/实现边界”说明。

证据更新：初始假设 H1 公共 UI 规范缺失 50%，H2 信息结构持续堆叠 35%，H3 后端性能导致体验差 15%。源码显示裸按钮/不同 scoped 间距、冗余页头及开发文案；本地生产构建的真实 API 操作链成功，当前证据支持 H1/H2 为主因（合计 >90%）。线上认证返回 401，未测量线上性能，不据此否定 H3 的可能性。

### 2. Why Fixes Failed (if applicable)
此前移动端修复解决的是 980px 溢出与标题挤压；其浏览器门槛不能单独验证信息层级、控件一致性和高级面板展开后的体验。没有证据表明此前针对这次视觉问题进行过失败修复。

本轮验收曾被测试选择器阻断：精确 label 文本不等于 select 的可访问名称。读取浏览器可访问树及定位计数后，改按 combobox 名称定位。另一次模板闭合错误由生产构建发现并修复；没有通过跳过检查绕开。

### 3. Prevention Mechanisms
| Priority | Mechanism | Specific Action | Status |
|----------|-----------|-----------------|--------|
| P0 | Architecture | variables/base 与公共 Panel/Metric/Status 统一控件体系 | DONE |
| P0 | Documentation | 新增 workbench-ui.md，索引接入并同步模板 | DONE |
| P0 | Test Coverage | 本地真实创建/发布/HTTP运行/诊断及套件引用贯通 | DONE |
| P1 | Test Coverage | 六路由九视口，默认/展开两状态、搜索空态、取消丢弃输入、API错误 | DONE |
| P1 | Code Review | 检查常用操作路径、文案层级、折叠字段可达性及截图位置 | DONE |

### 4. Systematic Expansion
- **Similar Issues**: 用例、套件、环境、调度、运行证据都存在新增功能直接追加表单的趋势；本轮统一基础样式并组织辅助能力。
- **Design Improvement**: 列表与编辑共享原始资产数据；搜索只改变显示集合；初次加载选择资产时检查 dirty，保留正在输入的内容。真实/模拟与发布证据语义沿用原契约。
- **Process Improvement**: 截图回页首，另查高级区域；等待非空数据再测布局。构建、几何检查、交互检查、视觉审查分别记录，避免互相替代。

### 5. Knowledge Capture
- [x] 新增 .trellis/spec/frontend/workbench-ui.md，记录控件、编辑状态和验收契约。
- [x] 更新 frontend/index.md 的条件指针。
- [x] 同步 src/templates/markdown/spec/frontend/。
- [x] 落盘本复盘与浏览器验收证据。
- [x] 规范更新通过独立提交保存；工作区原有业务改动保留。

验证命令和最终截图见 [验收记录](reviews/2026-10-26-workbench-ui/verification.md)。
线上链接需要访问认证，本轮未部署或验证远端新产物；隔离 API 仅调用本地 /check。

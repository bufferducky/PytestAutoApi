# 前端规范：PytestAutoApi

作用域：`platform/frontend/`（Vue 3、TypeScript、Pinia、vue-router）。
修改布局、导航、表单、表格或运行证据展示前，读取
[响应式布局与验收](./responsive-layout.md)。
修改 API 字段时，同时读取后端对应契约。

质量门槛：TypeScript / 生产构建、现有前端可靠性检查、真实浏览器布局回归。
构建成功与 HTTP 200 只说明产物可生成/访问，不证明移动端布局可用。

修改资产表单回填/套件引用时，读取 [资产编辑器回填](./asset-editor.md)。

修改页面信息层级、公共控件或资产搜索/编辑状态时，读取 [工作台交互与视觉约束](./workbench-ui.md)。

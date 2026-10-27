# 实施前真实浏览器基线

2026-10-27 在当前工作区运行；尚未接入 Element Plus、未修改产品代码。此记录证明现有功能基线，不代表本任务体验重构已完成。

## 命令与结果

```sh
PYTA_RUN_BROWSER_TESTS=1 PYTA_BROWSER_EVIDENCE_DIR=.trellis/tasks/10-27-frontend-ux-component-library/research/baseline .venv/bin/python -m pytest tests/backend/test_platform_frontend_browser.py -q -s
```

实际结果：`1 passed in 20.68s`；完整输出见同目录 `browser.log`，截图由测试直接生成。

| 现有覆盖 | 结果 |
| --- | --- |
| 创建、保存、预检、发布、本地真实 HTTP 运行及证据 | 通过 |
| 断网后显式错误 | 通过 |
| 默认/展开布局检查 | 48 次通过 |
| 页面未处理脚本错误 | 0 |
| 问号悬停、键盘、不改变表单 | 通过 |
| 未保存草稿调试、取消正式运行保留编辑 | 通过 |
| 环境变量类型保持、调度目录/预览/重置 | 通过 |
| 手册 | 44 篇、161 个主题、23 个实际渲染图形 |
| 手册新标签页、键盘、未保存输入、搜索/锚点/刷新/历史 | 通过 |
| 公司业务调用 | 无；使用隔离本地 API/SQLite 与本地业务端点 |

## 范围限制

本测试仍使用原生表单/确认和旧页面结构；不覆盖新组件库、新步骤工作区、隐藏标签页校验及异步确认的全部风险。本轮实施后必须新增/适配这些交互，不能复用本结果声称重构验收完成。

## 当前截图人工审查

已查看 1440px 的用例、结果、环境默认截图。用例页仍连续铺开步骤设置，环境/身份入口仍在折叠区。运行列表在 7 条非空记录下环境列过窄，中文环境名逐字竖排，状态标签在最右侧被局部裁切；该页面虽通过自动几何检查，视觉可读性仍不合格。对应 UX13、AC02/AC09/AC15，实施后需合理重排列与元信息并人工复查，不能仅以整页无横溢出判断成功。

## 已核实接口边界

运行列表 API 的真实参数位于 `platform/backend/src/pyta_platform_backend/api/routes/runs.py:31`，包含 limit/offset、environment_id、target_id、build、transport_mode、scenario_id/version、status、category、since/until，无关键词参数。新 UI 的关键字检索如不改后端，只能明确表示当前页过滤，不能声称全量搜索。

`services/diagnostic_service.py:389` 对时间要求带时区 ISO，版本筛选须同时提供 scenario_id。日期/时间组件转换必须保持该契约，不能直接提交不带时区的本地字符串。

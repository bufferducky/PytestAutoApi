# 响应式布局与验收

## 可执行约束

- 页面主容器与 Grid/Flex 子项使用可收缩轨道及 `min-width: 0`。
- 标题与可变长元信息并排时使用可换行 Flex，或为双方提供受约束的 Grid 轨道；
  `minmax(0, 1fr) auto` 会允许元信息把中文标题列压到 0px。
- 侧栏使用 `auto auto 1fr` 行分配；品牌区与导航项保持内容高度，底部承担留白。
- 应用壳和页头在 1080px 及以下切换为纵向布局；主导航保持六个入口可达。
- 表单字段、原生 select、fieldset 和标签都允许收缩；长 ID/说明文本可换行。
- 宽表格放入 `.table-shell`，原始证据 `pre` 在自身区域滚动。
  保留完整数据；不能用全页 `overflow-x:hidden` 掩盖内容被裁切。
- 保留 viewport meta，同时验证手机浏览器“桌面站点”常见的 980px 布局宽度。
  不能仅靠设备名称或 960px 以下的媒体查询判断适配成功。

## 真实浏览器回归

复用 `tests/frontend/responsive-layout.mjs` 的 `widths`、`routes`、
`measureLayout` 和 `assertLayout`。每个视口访问六个主路由，等待数据渲染后测量：

1. `documentElement.scrollWidth <= clientWidth + 1`。
2. 六个主导航链接存在；品牌区高度 < 100px，单个导航项高度 < 120px。
3. hero 标题宽度至少为 `min(240px, 内容区宽度 - 80px)`，高度 < 250px。
4. 运行页必须包含非空运行详情与诊断；用例页须包含长标签及原生选择控件。
5. 检查 320、390、768、960、980、1080、1081、1280、1440px，
   尤其断点两侧；保存 390px 与 980px 截图做视觉验收。

浏览器工具可以直接将 `measureLayout` 传给只读 `evaluate`，
将结果传给 `assertLayout`。使用 Playwright 时，设置 viewport 后依次导航并调用同一组函数。
发布时再检查实际构建产物，避免仅验证 Vite 开发服务器。

## 2026-10-25 缺陷证据

980px 视口实测标题宽度 0px、hero 高度 2225.75px、品牌区高度 984.04px；
与用户手机截图一致。修复后相同视口标题宽度约 482px、高度约 58px，
品牌区与导航项均为 48px；54 组本地页面/宽度检查通过。
完整复盘见 `docs/bug-analysis-mobile-layout.md`。


## 非空数据边界（2026-10-26）

真实创建运行后再检查首页/运行页；空库通过不能证明长 UUID、非空 JSON 和诊断表格可收缩。首页运行卡片的 Flex 子项须 min-width:0/可换行，长 ID 和运行详情有明确换行或局部滚动。tests/backend/test_platform_frontend_browser.py 已将默认表单创建的真实运行带入六路由/九宽度检查，不能先清空数据来规避。

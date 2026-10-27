# 使用手册与就地帮助契约

## 作用域与入口

作用域为 `platform/frontend/src/content/manual/`、`pages/ManualPage.vue`、`components/manual/` 及公共 `HelpHint.vue`。

- 用户面向不熟 HTTP/JSON 的业务新手；首版覆盖所有现有菜单与高级功能，不以只有菜单、占位页或短提示复制充当手册。
- 问号保留短说明，“查看完整手册”在新标签页打开对应小节；原配置页不切路由、不保存、不丢未保存输入。
- 后续只要求桌面兼容，1280/1440/1920px 验收；不新增手机适配及触屏专项。

## 内容与地址

`catalog.ts` 导出 `manualGroups` 与 `manualArticles`，通过 `group`、`category`、文章组成三级目录。文章 ID 与 `articles/{id}.md` 文件名相同。

```ts
interface Article {
  id: string;
  title: string;
  group: string;
  category: string;
  summary: string;
  keywords: string[];
}
```

- 正文标题的稳定 ID 显式声明：`## 令牌字段路径 {#token-path}`。
- 路由为 `/manual/:articleId?`，定位地址为 `/manual/login#token-path` 等；实际文章/小节 ID 以目录及正文为准。
- `index.ts` 的 `parseManualMarkdown(source, articleId)` 同时产生渲染块、标题目录和搜索小节；不要另外维护标题到锚点的重复算法。
- `topicLinks.ts` 的 `manualTopicLinks` 完整覆盖 `HelpTopic`，每个映射包含 `articleId` 和 `sectionId`，指向真实、唯一、有实质说明的小节。
- 新增/删除帮助主题、文章、小节时同时更新映射和站内链接，不能把找不到的主题一律映射到首页。
- 受控 Markdown 正文随静态产物发布，不增加任意用户文档/HTML 上传入口。图形与阅读器延迟加载，普通业务问号只需要主题地址。

## 阅读与编辑边界

`HelpHint` 的 `.help-tooltip` 是可交互的非模态帮助区域。内层纯说明通过 `role=tooltip` 和 `aria-describedby` 关联触发器，链接是独立可聚焦节点。

- 触发器使用 `type=button`，点击不提交父表单，不切换 label 勾选或 summary。
- Tab 可从问号进入“查看完整手册”，焦点移入帮助区后不能立即隐藏；Escape、外部点击与组件卸载清理行为完整。
- 链接地址通过 Vue Router 解析，兼容部署 base，使用真实链接及 `target=_blank`、`rel=noopener`。
- 手册内文章/小节导航在该标签页内进行，浏览器前进后退和刷新可用。
- 文章正文与 Mermaid 异步加载会改变高度，深链接需在内容准备好及图形完成后定位，不能仅依赖路由全局置顶。

## 错误行为

| 输入/情况 | 可见结果 |
| --- | --- |
| 有效文章及小节 | 正文、小节目录与真实标题显示，定位到相应位置 |
| 未知文章 | 明确文章无法找到，提供回到入门/目录入口 |
| 有效文章、未知小节 | 保留正文，提示定位失败并提供当前目录 |
| 搜索无结果 | 清楚的无匹配说明，可换关键词或回目录 |
| 正文加载失败 | 显示失败原因和可重试入口，不伪造内容 |
| Mermaid 失败 | 图形失败提示和可查看源码，配套文字继续可读 |

## 内容维护

- 配置型小节包含：含义、填写入口、前置条件、示例、预期结果与常见错误。
- 英文标识对应中文释义；JSON、字段路径、参数和提取使用可理解的具体请求响应。
- 示例按当前界面、模型、编译器/执行消费者和测试核对。特别区分配置预检、真实登录查询、草稿调试、发布、真实运行与历史禁用能力。
- 服务端秘密引用、数据源、浏览器或设备依赖明确标记为前置准备，示例不包含真实秘密。
- Mermaid 展示关系、阶段和分支，字段精确定义用表格；图形有配套解释，不以大量图形替代步骤。

## 验证与反例

- `node tests/frontend/manual-content.mjs`：通过真实 Vite 运行时检查目录、全部主题、小节存在与唯一、站内链接和实际搜索。
- `tests/backend/manual_browser_support.py` 由真实工作台浏览器回归调用：键盘新标签页、原页草稿保护、直接打开/刷新/历史导航、搜索、逐篇正文与每张图真实 SVG。
- `tests/frontend/responsive-layout.mjs` 定义桌面宽度，实际测量导航、正文及局部滚动；不按 CSS 字符串推断界面可用。

错误：复制所有短提示为文章，把全部问号链接到总览，截图仅验证静态首页。

正确：字段级小节有具体例子，全量映射校验有效；在原配置页输入未保存内容后，用键盘打开对应小节并检查原输入保持，再逐篇验证图形和正文。

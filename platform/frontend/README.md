# 平台前端说明

这里是新测试平台的前端界面。

一句话理解它的职责：

**让测试同学用更少的操作完成更多日常工作。**

这意味着前端第一阶段不追求花哨，而是优先做好：

* 信息清晰
* 路径顺手
* 状态明确
* 扩展容易

---

## 1. 新手第一次进入这里，先做什么

建议按这个顺序：

1. 先看 [`docs/new-architecture-quickstart.md`](../../docs/new-architecture-quickstart.md)
2. 确认后端已经通过 `make backend-dev` 跑起来
3. 配好 `platform/frontend/.env.local`
4. 执行 `npm install && npm run dev`
5. 先打开 `/dashboard` 和 `/runs`

这样做的原因很简单：

* 这两个页面最能体现“前端已经接通平台骨架”
* 页面加载不依赖你先理解所有业务细节

---

## 2. 当前前端的定位

第一阶段前端主要服务 1-3 人的小测试团队，所以设计目标非常务实：

* 打开就知道现在平台整体情况
* 能快速进入用例、套件、环境、运行记录、调度任务
* 重要信息优先展示，不做复杂大而全的系统外壳

所以目前优先搭的是：

* 壳层布局
* 左侧导航
* 顶部页头
* 核心页面骨架
* 真实 API 模块与错误状态

---

## 3. 启动前必须知道的一件事

当前 `vite.config.ts` 已经内置了 `/api` 开发代理。

这意味着本地开发时如果你直接沿用：

```dotenv
VITE_API_BASE_URL=/api/v1
```

请求会默认被转发到 `http://127.0.0.1:8000` 的 FastAPI，而不是打到前端开发服务器自己身上。

如果你的后端不跑在本机 `8000` 端口，再额外覆盖代理目标即可。

### 推荐的 `.env.local`

先复制模板：

```bash
cd /Users/ys/PyCharmProject/PytestAutoApi/platform/frontend
cp .env.example .env.local
```

再把 `.env.local` 改成：

```dotenv
VITE_API_BASE_URL=/api/v1
```

如果你的后端地址不是默认的 `http://127.0.0.1:8000`，再补一行：

```dotenv
VITE_DEV_PROXY_TARGET=http://127.0.0.1:9000
```

前端仅连接真实后端；连接失败会显示错误，不提供演示开关或替代数据。

---

## 4. 启动方式和最小验证

### 启动命令

```bash
cd /Users/ys/PyCharmProject/PytestAutoApi/platform/frontend
npm install
npm run dev
```

默认访问地址：

```text
http://127.0.0.1:5173
```

如果你在仓库根目录，也可以直接：

```bash
make frontend-dev
```

### 最小验证路径

建议先验证这两个页面：

1. `http://127.0.0.1:5173/dashboard`
2. `http://127.0.0.1:5173/runs`

如果你已经按后端文档创建过一条 run，那么这里应该能看到记录。

### 最小构建验证

```bash
cd /Users/ys/PyCharmProject/PytestAutoApi/platform/frontend
npm run build
```

这个命令除了打包，还会顺带做 TypeScript 检查，适合作为前端改动后的最小自检。

---

## 5. 目录结构怎么理解

### `src/router/`

这里管理页面路由。

路由的价值不只是“跳页面”，还承担页面元信息的统一来源，例如：

* 当前页面标题
* 页面说明
* 导航高亮

如果这些信息散落在多个文件里，后面会很难维护。

### `src/api/`

这里是前端请求后端的统一入口。

要点是：

* 页面尽量不要自己直接写 `fetch`
* 仅请求后端持久化数据，不生成替代数据
* 统一处理错误和返回值结构

这样后面后端接口字段变化时，不需要满项目到处找调用点。

### `src/stores/`

这里是 Pinia 状态管理。

当前主要承载壳层级共享状态，例如：

* 当前所在模块
* 导航信息
* 仪表盘加载状态

不是所有数据都要放 store。

简单原则是：

* 只有多个页面/组件共享、并且有持续状态价值的数据才放 store

### `src/pages/`

这里是一页一个页面组件。

第一阶段页面的重点不是做完所有表单，而是先把每个页面的职责边界立住。

例如：

* 仪表盘：看全局情况
* 用例页：管理结构化用例
* 套件页：管理组合执行入口
* 环境页：管理 base_url 与鉴权策略
* 运行页：看运行记录与排障入口
* 调度页：管理计划任务

### `src/components/`

这里放可复用组件。

例如：

* 壳层组件
* 指标卡
* 状态标签
* 通用占位容器

如果某个页面里的块明显可以在别处复用，就应该考虑往这里提。

---

## 6. 真实数据与历史

新运行、计划预览及调度定义均提交 `transport_mode: live`。请在资产面板选择已发布版本并核对契约与写入范围；不提供样例套件快捷运行或演示资产导入。

历史模拟运行保留原标识，不代表真实业务通过。新评估已禁用，既有评估报告仍可通过 run ID 查询和对比。

---

## 7. 推荐阅读顺序

如果你想用一条最短路径把前端读明白，建议按这个顺序：

1. `src/router/index.ts`
2. `src/layouts/AppShell.vue`
3. `src/components/layout/AppHeader.vue`
4. `src/components/layout/SideNav.vue`
5. `src/pages/DashboardPage.vue`
6. `src/pages/RunsPage.vue`
7. `src/api/client.ts`
8. `src/api/modules/dashboard.ts`
9. `src/api/modules/management.ts`
10. `src/stores/dashboard.ts`

这样你会更容易看明白：

* 页面怎么进来
* 数据怎么请求
* 真实接口与错误如何传递
* 页面状态为什么这么组织

---

## 8. 第一阶段最重要的页面

虽然前端骨架已经有多页，但第一阶段最优先做深的其实是两个：

1. **仪表盘**
2. **运行记录页**

原因很现实：

* 仪表盘是用户进入平台后的第一站
* 运行记录页最终会成为测试排障的第一入口

这两个页面一旦做好，平台的“日常使用价值”会最快显现出来。

---

## 9. 新手最常踩的坑

### 坑 1：页面开了，但接口都报错

通常是因为你没有把 `VITE_API_BASE_URL` 改成 `http://127.0.0.1:8000/api/v1`。

### 坑 2：仪表盘没有数据

仪表盘只读取 `/dashboard/overview`。空数据库显示空态；接口不可用显示错误，不通过运行列表拼装统计。

---

## 10. 后续最自然的增强顺序

接下来前端最自然的演进顺序通常是：

1. `runs / dashboard` 继续贴近真实接口
2. `cases` 页面补列表、筛选、详情
3. `environments` 页面补编辑表单
4. `schedules` 页面补创建/启停
5. `suites` 页面补组合与排序

这个顺序的好处是：

先做最能直接体现提效的页面，再逐步补全配置型页面。

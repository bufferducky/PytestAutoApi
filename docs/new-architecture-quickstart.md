# PytestAutoApi 启动指南

本指南从仓库根目录操作，启动页面工作台与真实后端。日常路径是“配置环境 → 编辑场景 → 调试 → 发布 → 回归 → 查看结果”，结构与代码入口见 [开发导览](getting-started-modernized.md)。

## 1. 安装依赖

准备 Python 3.9+、Node.js 22.12+（当前 Vite 也支持 Node 20.19+）和可连接的独立 MySQL 数据库。Python 依赖以 [pyproject.toml](../pyproject.toml) 为准，前端依赖以 [package.json](../platform/frontend/package.json) 与锁文件为准。

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-dev
npm ci --prefix platform/frontend
```

后续命令均在仓库根目录执行。浏览器/移动端能力属于可选扩展，普通 API 工作台启动不要求安装浏览器或 Appium。

## 2. 配置 MySQL 并执行 Alembic

先创建独立平台数据库和有相应权限的账号。该库保存测试平台状态，与被测业务数据库分别配置。在准备启动后端的终端设置实际值：

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_DATABASE=pyta_platform
export MYSQL_USER=pyta
export MYSQL_PASSWORD='<填写本地数据库密码>'
```

也可设置 `PLATFORM_BACKEND_DATABASE_URL=mysql+pymysql://...`；该变量优先于 `MYSQL_*`。密码含特殊字符时优先使用独立 `MYSQL_*` 字段，由后端构造连接 URL。后端从进程环境读取配置，前端的 `.env.local` 不会替后端加载数据库变量。

在同一终端执行结构升级后启动：

```bash
python -m alembic -c platform/backend/alembic.ini upgrade head
make backend-dev
```

开发和生产必须配置 MySQL，缺失配置会启动失败；数据库表结构由 Alembic 管理。SQLite 仅供离线测试与历史迁移，不是本地产品启动方式。迁移已有实例时先看 [MySQL 迁移手册](mysql-migration.md)，保留历史数据和附件。

默认后端地址 `http://127.0.0.1:8000`。在另一终端验证：

```bash
curl --fail http://127.0.0.1:8000/api/v1/health/live
curl --fail http://127.0.0.1:8000/api/v1/dashboard/overview
```

`make backend-dev` 已设置应用包所需的 `PYTHONPATH`。后端启动时管理 `WorkerHost` 与实际 `ScheduleHost` 的生命周期，无需额外启动旧调度器。

## 3. 启动前端

在另一终端、仓库根目录执行：

```bash
make frontend-dev
```

默认打开 `http://127.0.0.1:5173`；端口被占用时以终端输出的实际地址为准。[vite.config.ts](../platform/frontend/vite.config.ts) 当前内置 `/api` 开发代理，默认转发到 `http://127.0.0.1:8000`，无需额外反向代理即可使用 `/api/v1`。

需要覆盖配置时，在 `platform/frontend/.env.local` 中设置（模板见 [.env.example](../platform/frontend/.env.example)）：

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000
```

修改后重启 Vite。代理仅用于开发；生产构建的 API 转发由部署反向代理提供，见 [部署说明](../deploy/README.md)。前端连接真实后端，接口不可用会显示错误。

## 4. 用页面完成第一次真实回归

1. 打开 **工作台** 和 **执行结果**，确认数据加载正常。全新数据库显示空态，需要自行创建资产。
2. 在 **环境管理** 配置测试环境、目标系统、测试身份与项目绑定。秘密通过后端运行环境注入，页面填写引用；平台 MySQL 连接不作为被测接口地址。
3. 在 **用例管理** 创建场景，编辑请求、断言、变量提取与依赖。也可通过旧 YAML 内容导入入口生成草稿；导入本身不发业务请求，需人工核对转换结果。
4. 使用 **调试当前整场景** 或 **仅调试此步骤** 验证当前草稿。调试会真实发送请求，不自动保存或发布；单步骤缺前置输出时提供本次 inputs。
5. 保存 → 预检 → 发布不可变版本，选择环境与构建后正式执行。预检检查定义与执行条件，不表示业务请求已通过。
6. 在 **执行结果** 查看状态、失败步骤、断言差异、脱敏请求响应和清理证据。调试记录单独标记，不计入正式回归与发布证据。
7. 需要组合或定时回归时，在 **套件管理** 固定已发布版本，再到 **调度任务** 配置、预览并启用计划。

页面新运行显式提交 `transport_mode=live`；调用普通运行 API 时还须显式指定适用的 `execution_mode=standard_run` 或 `legacy_yaml`。不要用运行已受理、健康检查成功或页面可访问代替业务断言结果。

## 5. 检查与排障

```bash
make test-new
make frontend-build
```

前者运行引擎、兼容层与平台后端回归，后者执行 TypeScript 检查与生产构建。默认离线测试使用隔离测试存储和受控传输，不验证你的业务环境；真实 MySQL 集成需要独立配置，跳过项应单列。

| 现象 | 检查位置 |
| --- | --- |
| 后端缺数据库配置或连接失败 | 确认后端终端已导出 MySQL 变量、库和账号已创建且可访问 |
| 数据库结构不兼容 | 在相同数据库环境下执行 Alembic 升级 |
| 找不到 `pyta_platform_backend` | 激活 `.venv`，回到根目录用 `make backend-dev` |
| 页面请求失败 | 检查后端健康、浏览器网络请求、`.env.local` 的 API 路径和代理目标 |
| 工作台没有运行 | 新库空态正常；自行创建并运行场景，刷新执行结果 |
| 重启后看不到原记录 | 核对是否连接同一 MySQL 数据库；附件另检查 `PLATFORM_BACKEND_ARTIFACT_ROOT`，默认 `.runtime/artifacts` |

浏览器与移动端旅程代码保留，需单独安装可选依赖并满足浏览器/设备预检；部分查询旅程的验证不能代表完整业务和真机验收。新评估执行禁用，历史评估仍可查询。扩展能力与后续建设范围见 [后端说明](../platform/backend/README.md) 和 [项目导览](getting-started-modernized.md)。

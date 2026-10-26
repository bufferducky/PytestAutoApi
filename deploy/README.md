# Docker Compose 部署

先在 `platform/frontend/` 执行 `npm ci`，再执行
`VITE_API_BASE_URL=/api/v1 npm run build -- --mode production`。
将项目的 `src/`、`platform/backend/src/`、`platform/frontend/dist/`、
`platform/backend/alembic.ini`、`platform/backend/alembic/`、
`pyproject.toml`、`README.md` 和 `deploy/` 同步到服务器的独立发布目录。

首次从 SQLite 切换必须先完成 [MySQL 迁移手册](../docs/mysql-migration.md)。
下面的启动命令仅适用于已核对迁移结果的实例或全新空实例。

在 `deploy/` 下准备 `.htpasswd`（Nginx Basic Auth），并配置 `.env`：

`.htpasswd` 需要容器内 Nginx worker 可读（`chmod 644 deploy/.htpasswd`）。
它只保存密码哈希；明文账号文件不要上传到站点目录或提交 Git。

```dotenv
HTTP_PORT=18080
RELEASE_TAG=20261025
MYSQL_DATABASE=pyta_platform
MYSQL_USER=pyta_platform
# 在服务器安全填写两个独立强密码，不提交真实值。
MYSQL_PASSWORD='<application-password>'
MYSQL_ROOT_PASSWORD='<root-password>'
```

在服务器发布目录执行：

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env config --quiet
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env ps
docker compose -f deploy/compose.yaml --env-file deploy/.env logs --tail 100
```

每次更新使用新的发布目录和 `RELEASE_TAG`，保留旧目录和镜像。
Compose 项目名固定为 `pytestautoapi`，保留 `platform-data` 中的旧 SQLite 和执行证据；
MySQL 8.4 使用独立 `mysql-data` 卷且不发布宿主机端口。
后端等待数据库健康后先运行 Alembic upgrade head，成功才启动单 worker API。
禁止使用 `down -v`。数据库结构升级前先停写并备份两个卷。
切回旧 SQLite 不包含 MySQL 新写入，回滚必须按迁移手册先保护新数据。

数据库账号通过独立 MYSQL_* 环境字段传入，由后端安全构造 SQLAlchemy URL；
不要在 Compose 中拼接带密码的 URL。`.env` 使用单引号保存字面量（尤其 `$`、`#`），
复杂引号按 Compose dotenv 规则转义，权限设为 600。只运行 `config --quiet`，避免输出凭证。
新评估执行已禁用，历史评估报告仍可读取；历史模拟结果不代表真实业务验证。

Compose 默认构建 Chromium 能力（INSTALL_WEB_RUNNER=1）；独立 Docker 构建默认仅 API。Android/Appium 不包含在当前部署镜像中。
业务环境和密钥通过平台/运行时另行配置，不打包本地历史配置或状态库。

## 154 主机历史部署记录（本次未部署）

- 访问入口：`https://test.ysspace2099.com`
- 备用 IP 入口：`http://154.40.58.145:18080`
- SSH：`ssh us-vps`
- 发布目录：`/home/ubuntu/pytestautoapi/releases/20261025-mobile-1725`
- 当前版本软链接：`/home/ubuntu/pytestautoapi/current`
- 本机账号记录：`deploy/access.txt`（已忽略，不提交）
- 首次验证：本地 238 passed / 2 skipped，生产前端构建通过；
  远端登录保护、健康检查、仪表盘 API、mock 登录套件通过。

```bash
ssh us-vps
cd /home/ubuntu/pytestautoapi/current
docker compose -f deploy/compose.yaml --env-file deploy/.env ps
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
```

### Cloudflare 域名与 HTTPS

复用 154 主机现有的 `cpa` Tunnel（系统服务 `cloudflared`）。
Cloudflare 控制台的该隧道内维护一条已发布应用路由：

- 主机名：`test.ysspace2099.com`
- 服务：`http://127.0.0.1:18080`
- DNS：CNAME 指向 `ccde8e76-b600-453b-985d-df2046592650.cfargotunnel.com`，已代理
- HTTPS 由 Cloudflare 提供，平台仍要求原 Basic Auth 账号密码

更新 Compose 不需要修改这条路由。排查域名时分别检查
`systemctl status cloudflared` 和 Compose 容器状态。
隧道由其他应用共享，不要删除隧道或覆盖原有根域名路由。

### 2026-10-25 手机布局修复

已使用 Compose 更新 web 容器。当前前端修复了 980px 下标题被压成单字列、
侧栏拉伸和窄屏页面横向溢出；生产构建在六个路由、九种宽度下共 54 组检查通过。
后端沿用 `pytestautoapi-backend:20261025-1700`，数据卷继续复用。
回滚前端时进入 `/home/ubuntu/pytestautoapi/releases/20261025-1700`，执行：

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --no-build web
ln -sfn releases/20261025-1700 /home/ubuntu/pytestautoapi/current
```

## 2026-10-25 MySQL 与真实执行改造（历史发布）

- 当前目录：`/home/ubuntu/pytestautoapi/releases/20261025-mysql-live-v1`；`current` 已切换。
- 后端镜像：`pytestautoapi-backend:20261025-mysql-live-v1`。
- MySQL 8.4.13，独立 `pyta_platform` 库、`pytestautoapi_mysql-data` 卷；不映射公网端口。
- 数据库配置位于该目录 `deploy/.env`（600 权限）；原登录保护保持不变。
- 源库和附件卷保留；切换前停写备份位于 `/home/ubuntu/pytestautoapi/backups/20261025-before-mysql-v1/`。
- 迁移了服务器10条记录：环境2、草稿2、上下文2、调度2、运行1、保留策略1；没有已保存的报告/附件文件。重复导入新增0条，无冲突/孤立关联。
- 旧调度均暂停，旧运行仅作演示历史，真实统计为0；新模拟执行400，评估新执行409。
- 后端重启后数据、历史标识与暂停状态保持；MySQL/backend健康，公开HTTPS仍要求原认证。
- 本地全量验证267通过、2可选测试跳过；前端类型检查、构建及可靠性检查通过。尚未进行公司业务接口联调。
- 详见 `docs/mysql-migration.md`。MySQL 接收新写入后，不能直接切回旧SQLite并宣称无损。


## API/Web 查询接续发布

当前工作树增加了言迹测试 API/Web 查询接入，操作与限制见 `docs/yanji-query-workbench.md`。Compose 的 `INSTALL_WEB_RUNNER` 默认 1，可选构建 Chromium；置 0 仅提供 API 能力，Web 预检会报告缺驱动/浏览器。配置的 Chromium 基线必须使用该镜像 `/api/v1/runner-capabilities` 返回的版本，不能沿用另一台机器的浏览器版本。

秘密按 Compose 中的四个 PYTA_SECRET_YANJI_* 引用注入，值只保存在服务器受限环境配置，仓库不包含值。运行时研究清单已随 Python 包交付；旧 YAML 通过内容导入，不要求容器存在本机 data 目录。2026-10-26 已部署此能力，当前版本及验证记录见下节。


## 2026-10-26 API/Web 查询版本（历史发布）

- 入口：`https://test.ysspace2099.com`；平台登录保护沿用原配置。
- 当前目录：`/home/ubuntu/pytestautoapi/releases/20261026-apiweb-181749`；镜像 `pytestautoapi-backend:20261026-apiweb-181749`。
- 备份：`/home/ubuntu/pytestautoapi/backups/20261026-apiweb-181749`，包含停写后的 MySQL dump、原状态/附件卷、旧配置与 SHA-256 核对文件。
- 沿用原 MySQL/附件卷，切换后核对保留环境3、场景5、套件1、目标3、运行4的原ID；没有重放旧任务。
- 新增测试环境与 API/Web 两组身份/项目引用，发布4个真实查询场景、查询套件和 Web 查询旅程；秘密仅保存在服务器600权限环境配置。
- 部署后 API run `62b5314b57684d9098e35fe938dc5b61`：4场景/12断言通过；Web run `7aea5886f7d84654868540261968cbeb`：8步/6断言通过，Chromium156.0.8078.4，清理成功。仅使用言迹测试环境。
- HTTPS未认证401、原认证后200；公网JS与本地生产构建SHA-256一致，worker健康，16项契约和Chromium能力可读取。
- 本次修复发布解包权限：源码/静态产物使用正常可读权限，Dockerfile在USER app前规范化/app/src及/app/platform/backend；秘密配置始终600，不能对deploy目录递归放宽权限。

回滚应用时使用保留的上一发布目录及镜像，复用当前MySQL/附件卷。新查询记录/配置已经入库，不能直接覆盖数据库备份而丢失新数据。先停新触发、核实运行结束，再在上一目录执行 `docker compose ... up -d --no-build --no-deps backend web` 并切回current链接；不得down -v。

完整四组业务写入/恢复、隔离及W01—W04仍未全部验收，本次部署不改变这些范围事实。

## 2026-10-27 个人接口工作台（当前发布）

- 代码提交：`b694ce5`，已推送 `master`。
- 当前目录：`/home/ubuntu/pytestautoapi/releases/20261027-workbench-010909`；后端镜像同名tag。
- 备份：`/home/ubuntu/pytestautoapi/backups/20261027-workbench-010909`，MySQL停写停库后冷备份及附件卷归档；不覆盖已有数据。
- 前后端一起更新，新增未保存草稿调试；调试记录不作正式回归证据。仍使用现有MySQL JSON字段，Alembic保持0001_mysql。
- 环境4、场景9、套件2、运行6、调度3原ID全部保留；启动兼容逻辑为已有环境补建1个默认target，没有新增业务运行。
- 公网原认证保持，七页面及手机/桌面布局正常，资源SHA-256与本地构建一致，worker健康、Chromium156.0.8078.4可用。
- 旧发布目录和镜像保留。应用回滚复用当前MySQL/附件卷，不执行down -v、不覆盖数据库备份。
- 详细发布与验收回执：`docs/reviews/2026-10-27-workbench/`。

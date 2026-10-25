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

默认安装接口测试能力；浏览器/Appium 扩展及其运行环境未包含在此镜像中。
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

## 2026-10-25 MySQL 与真实执行改造（当前发布）

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

# 服务器 SQLite → MySQL 8.4

本手册用于服务器现有实例停写迁移，不是已完成部署记录。唯一来源是服务器
`pytestautoapi_platform-data` 卷中的 SQLite 和附件；不上传或合并本地 `.runtime/`。
保留 ID、版本、关联、时间及历史模式；导入历史不会重新执行请求、恢复旧队列或重放调度。
迁入调度必须保持暂停，旧 queued/running 仅作历史保存并标记不恢复。
历史 Mock/未知模式不能改为 live，新运行只允许真实执行。新评估执行禁用，历史报告可读。

以下命令在服务器的新发布目录运行，凭证仅由受保护的 `deploy/.env` 注入。
所有 Compose 命令都使用同一个项目名；不要执行 `down -v`。

## 1. 停写与备份

预先保留旧发布目录、镜像标签和 Compose 配置。安排停写窗口，停止旧版本
web 和 backend，确认没有其他 worker、CLI 或外部进程写库或附件。
等待后端正常退出（Compose 给出 60 秒宽限）；强杀后先检查 SQLite 完整性。

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env stop web backend
```

使用服务器备份工具对已停止写入的完整 `platform-data` 卷做离线备份，包含
`platform-state.sqlite3`、可能存在的 WAL/SHM、附件目录、日志和报告。
通过 SQLite backup API 从服务器源生成一致快照并执行 `PRAGMA integrity_check`；
不能只复制活跃 SQLite 主文件。记录服务器源位置、备份时间、文件清单、大小和 hash，
在受保护目录保留可恢复副本；先验证恢复副本可读，再继续。
确认历史附件实际位置；若不在 `/state/artifacts`，从服务器备份复制到该目录并保持
相对路径，原文件保留。缺失或损坏附件必须记录，不能生成替代证据。

## 2. 配置与目标建库

按 `deploy/README.md` 配置 `.env`（权限 600）。使用专用非 root 应用账号，
MYSQL_HOST=mysql、MYSQL_PORT=3306 由 Compose 注入。后端使用 MYSQL_USER、
MYSQL_PASSWORD、MYSQL_DATABASE 安全构造 `mysql+pymysql` SQLAlchemy URL，
保留密码中的 `@:/?#%$` 等字符，不在 shell 或 Compose 拼接连接串。
独立部署时也可由受控环境提供已正确编码的 `PLATFORM_BACKEND_DATABASE_URL`。
附件根独立固定为 `PLATFORM_BACKEND_ARTIFACT_ROOT=/state/artifacts`。

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env config --quiet
docker compose -f deploy/compose.yaml --env-file deploy/.env build backend
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d mysql
docker compose -f deploy/compose.yaml --env-file deploy/.env run --rm --no-deps backend python -m alembic -c platform/backend/alembic.ini upgrade head
```

执行升级前确认 MySQL 已健康。MySQL 使用独立 `mysql-data` 卷，不映射宿主机端口。
已有目标库先备份，未知目标记录冲突不能覆盖。账号初始化变量只在首次空卷初始化生效，
修改 `.env` 不会自动修改已有数据库密码。

## 3. 预演、导入与核对

后端和 web 继续停写。CLI 覆盖镜像默认启动命令，因此不会启动 API/worker。

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env run --rm --no-deps backend python -m pyta_platform_backend.migrate_sqlite --source /state/platform-state.sqlite3 --artifact-root /state/artifacts --dry-run
docker compose -f deploy/compose.yaml --env-file deploy/.env run --rm --no-deps backend python -m pyta_platform_backend.migrate_sqlite --source /state/platform-state.sqlite3 --artifact-root /state/artifacts --apply
docker compose -f deploy/compose.yaml --env-file deploy/.env run --rm --no-deps backend python -m pyta_platform_backend.migrate_sqlite --source /state/platform-state.sqlite3 --artifact-root /state/artifacts --dry-run
```

保存受控迁移报告与源指纹，核对逐表数量、ID 集合、版本/hash、外键关联、配置、
运行结果、历史评估报告和附件索引。单独核对附件存在/缺失/损坏清单及文件大小/hash。
确认迁移账本完成、再次预演无冲突；相同源重复导入应跳过一致记录，不创建副本。
有差异立即停止切换，保留源和目标供排查，不通过删除目标记录掩盖冲突。
通过 DBX 的受控连接核对 MySQL schema 和计数（连接由运维配置，不公开 MySQL 端口）。

## 4. 切换与验收

只有核对通过才启动服务；启动自动执行 Alembic，失败时 API 不启动。

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d backend web
docker compose -f deploy/compose.yaml --env-file deploy/.env ps
```

检查登录保护、健康接口、真实目录、历史详情与附件；确认旧调度暂停、旧任务不领取，
新评估返回明确禁用。用已确认的配置创建真实资产/运行，再重启验证持久化与任务状态。
数据库不可用应明确失败，不能回退 SQLite 或演示数据。缺少真实业务凭证时记录
“业务联调未验证”，不以历史模拟成功或测试替身作为验收。

## 5. 回滚

切换前失败：保持停写，保留失败目标和报告，恢复经过验证的服务器备份及旧镜像，
使用旧版本原 Compose 启动。不要覆盖或删除原卷。

MySQL 已接收新写入：先停止 web/backend 和所有写入者，备份 MySQL、附件和迁移账本，
记录切换后新增/变更数据。旧 SQLite 不含这些记录，直接切回会丢失它们的可见性；
必须先制定对账、导出或前向修复方案并确认数据处置，再恢复旧服务。
没有自动 MySQL→SQLite 反向同步保证，不能宣称无损回滚。保留两个卷、旧镜像与备份，
不在迁移窗口执行历史保留期清理。

## macOS 发布包

从 macOS 打包时使用 `COPYFILE_DISABLE=1 tar --no-xattrs --exclude='._*'`，并保留
`.dockerignore` 的 `**/._*` 排除规则。AppleDouble 元数据文件若进入镜像的
`alembic/versions/`，会被误识别为迁移脚本。正式升级前先在镜像内执行：

```bash
docker run --rm --entrypoint python pytestautoapi-backend:<release-tag> -m alembic -c platform/backend/alembic.ini history
```

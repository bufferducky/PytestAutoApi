# 154 服务器标准发布 SOP

适用 PytestAutoApi 已运行实例的日常前后端更新。服务器是 `ssh us-vps`（154.40.58.145），站点是 https://test.ysspace2099.com，发布根目录 `/home/ubuntu/pytestautoapi`，Compose 项目名 `pytestautoapi`。

本流程使用新的发布目录和后端镜像，沿用服务器配置与两个数据卷。普通发布使用短暂停机的冷备份；提前安排操作窗口，直到 accept 完成前不要在页面编辑或执行任务。首次安装、数据库结构变更、数据库备份恢复走本文后面的专项流程。

## 1. 发布前检查

1. 明确本次变更、测试范围、回滚对象，提交代码并推送。记录代码提交号；发布文档后续另行提交。
2. 本地安装 `.venv` 开发依赖、Node/npm、Playwright 与 Chromium。服务器需要 Docker Compose v2、`flock`、tar、sha256sum；宿主机无需 Python，检查工具借用现有镜像。
3. 确认服务器当前服务健康。发布人员协调停止其他写入者，等待已有 queued/running 任务结束，并暂停启用的调度。脚本遇到活动任务或 active 调度会拒绝切换，**不会替你取消任务或暂停计划**。
4. 凭证保存在服务器 `current/deploy/.env`（600）、`.htpasswd`（644）。本机 `deploy/access.txt` 或权限600的 JSON 凭证文件仅用于公网验收，不上传、不提交。JSON 格式为 `{"username":"…","password":"…"}`。

```bash
ssh -o UpdateHostKeys=no us-vps 'readlink -f /home/ubuntu/pytestautoapi/current; docker ps --filter name=pytestautoapi --format "{{.Names}} {{.Image}} {{.Status}}"'
```

检查通过标准：明确当前目录/镜像，MySQL、backend 健康，web 正常，已协调停写窗口。不要输出完整 `docker compose config` 或 `docker inspect`，它们可能包含环境秘密。

## 2. 从指定提交构建发布包（本地）

在仓库根目录，设置本次唯一 tag 和本地输出目录。以下 tag 仅为示例，每次改成新的日期、用途及短提交号，长度最多64字符。变量在同一终端继续使用。

```bash
revision=$(git rev-parse HEAD)
tag="20261028-update-$(git rev-parse --short HEAD)"
bundle="/private/tmp/pyta-release-$tag"

# 只查看计划，不构建、不写文件
python3 deploy/scripts/release.py --revision "$revision" --tag "$tag" --output "$bundle" --plan

# 真实执行本地构建和检查，不连接服务器
python3 deploy/scripts/release.py --revision "$revision" --tag "$tag" --output "$bundle"
```

工具要求工作树干净，Git 归档到隔离目录；不会将本机 `.env`、历史状态库、node_modules、旧 dist 或 AppleDouble 文件带入源码包。依次执行 npm ci、Ruff、Python 回归、生产前端构建、三组前端脚本和显式工作台浏览器测试。任一步失败退出，不生成可发布 manifest/bundle；输出目录保留本地检查日志，换新目录重试。

产物为 `bundle.tar.gz`，内含 `source.tar.gz`、`frontend.tar.gz`、`manifest.json` 和 `tools/`。manifest 绑定代码提交、实际产物与静态资源 SHA-256、工具文件哈希和检查结果；上传工具也来自该提交并在同一隔离目录检查。检查日志只在本地 `local-checks/`，不随包上传。真实 MySQL 自动化集成不在默认打包流程中，另行使用隔离测试库验证并记录。

通过标准：所有本地检查退出0，输出 bundle 的 SHA-256；确认 optional 跳过项及业务验收范围，不能把离线回归称为公司业务通过。

## 3. 上传并准备新目录

使用 SSH 标准输入传输，避免依赖服务器 SFTP。上传到新的 incoming/tag 目录；已存在目录会拒绝，禁止覆盖上次产物。

```bash
ssh -o UpdateHostKeys=no us-vps "mkdir /home/ubuntu/pytestautoapi/incoming/$tag" \
  && ssh -o UpdateHostKeys=no us-vps "cat > /home/ubuntu/pytestautoapi/incoming/$tag/bundle.tar.gz" < "$bundle/bundle.tar.gz"
```

首次使用本工具前先执行一次 `ssh us-vps 'mkdir -p /home/ubuntu/pytestautoapi/incoming'`。随后在本地计算并核对上传文件哈希，再解包：

```bash
shasum -a 256 "$bundle/bundle.tar.gz"
ssh -o UpdateHostKeys=no us-vps "sha256sum /home/ubuntu/pytestautoapi/incoming/$tag/bundle.tar.gz"
# 两边SHA相同才继续
ssh -o UpdateHostKeys=no us-vps "umask 022; tar -xzf /home/ubuntu/pytestautoapi/incoming/$tag/bundle.tar.gz -C /home/ubuntu/pytestautoapi/incoming/$tag"
```

进入服务器，设置相同 tag。服务器阶段脚本默认只显示计划；附加 `--apply` 才实际执行。

```bash
ssh us-vps
# 以下在154执行，填入与本地一致的tag
tag='20261028-update-填入实际短提交号'
root=/home/ubuntu/pytestautoapi
tool="$root/incoming/$tag/tools/server_release.sh"

sh "$tool" stage "$tag"
sh "$tool" stage "$tag" --apply
sh "$tool" build "$tag" --apply
```

`stage` 校验归档、拒绝越界/链接文件，创建 releases/tag，复制当前 `.env` 和认证哈希，仅更新 RELEASE_TAG。`build` 在切换前检查 schema 相同、构建新镜像，验证实际非root用户、16项契约/650条研究观察、Chromium启动及容器内本地HTTP worker执行/证据保存；不挂生产数据库或附件卷。通过后记录镜像ID、源码和配置指纹。stage后源码或配置改变会拒绝build，必须以新tag重新准备；启动后和accept前还会核对实际容器镜像ID，防止仅镜像tag正确而容器仍是另一版本。

通过标准：build 完成，`releases/tag/verification/` 有镜像、worker和build回执；线上仍为旧版本。阶段操作有文件锁，发现当前软链接与实际容器版本不一致会停止，避免交叉发布。保留 incoming/tag，activate/accept 还会重新核对原包。

## 4. 备份并激活（154）

```bash
sh "$tool" activate "$tag" --apply
```

脚本按顺序执行：

1. 再核对当前版本、schema、已验收镜像和配置，读取资产/环境/版本/运行内容指纹（多版本资源按ID＋版本保留每一版），确认无活动任务与启用调度。
2. 停止 web 封闭公网写入口，二次检查空闲和数据指纹；随后停止 backend、MySQL。
3. 核对实际卷名，冷备份 `pytestautoapi_mysql-data` 与 `pytestautoapi_platform-data`，检查 gzip/tar可读并核验SHA-256。备份目录700，归档和配置600。
4. 使用新目录启动同名项目的 mysql/backend/web，等待健康，再核对原ID及内容指纹。
5. 阶段标记 activated，**暂时保持旧 current 链接**，等公网验收。

备份在 `backups/tag/`。备份失败、新服务启动失败或数据不一致时尝试恢复操作前的应用，继续使用现有数据卷，返回非0；自动恢复也失败时立即转人工处理。无论成功失败都保留归档和发布目录。

通过标准：新镜像服务健康，所有原ID/内容指纹一致，queued=0、last_error为空。此时生产已运行新容器，不能因为 current 还指向旧目录就误以为未切换。

## 5. 公网验收并正式确认

回到保留 `$bundle` 和 `$tag` 的本地终端：

```bash
.venv/bin/python deploy/scripts/verify_public.py \
  --bundle "$bundle" \
  --url https://test.ysspace2099.com \
  --credentials-file deploy/access.txt \
  --browser
```

脚本只发GET请求，浏览器会阻止写请求及跨站请求。检查未认证首页/API返回401、认证健康和worker、16项契约、浏览器能力、入口静态资源完整列表及SHA匹配；浏览器检查7路由×9宽度的默认/展开区域、主导航、横向溢出及脚本/请求错误。成功或失败均写 `verification/public.json`，不会写业务数据、自动运行公司用例或修改 current。

不加 `--browser` 可先排查HTTP，但回执 `browser_passed=false`，不能用于 accept。扩展页已知品牌区偏高仅作为 warnings 明确记录；核心页同项仍严格失败，所有页面横向溢出/脚本错误严格失败。

验收成功后上传回执，在1小时内执行 accept。失败时按第6节回滚，不能手工把JSON的 passed 改成 true。

Cloudflare入口需要明确的发布检查User-Agent。公网验证将Cloudflare注入的已知统计脚本从发布资源清单中单独排除，并在验证浏览器中移除该统计标签，避免原标签的SRI校验误报，不发送外站请求；其他外部脚本仍拒绝，应用资源完整列表与SHA核验保持严格。浏览器代发请求显式携带本站Basic认证，跨源和重定向守卫先执行，避免反复401挑战导致误报。

```bash
ssh -o UpdateHostKeys=no us-vps "cat > /home/ubuntu/pytestautoapi/releases/$tag/verification/public.json" < "$bundle/verification/public.json"
ssh -o UpdateHostKeys=no us-vps "sh /home/ubuntu/pytestautoapi/incoming/$tag/tools/server_release.sh accept $tag --apply"
```

accept 重新核对镜像/源码/配置与数据，要求回执绑定同一 manifest、提交、tag、站点且浏览器通过，然后原子更新 current。

通过标准：current指向新目录，实际容器对应新目录/镜像；HTTP/浏览器回执通过，已知问题和未验收范围单列。

## 6. 应用回滚

适用于同schema的应用退回，既可在 activated 尚未accept时执行，也可在accept后执行。tag 是**本次要退回的候选版本**，不是上一版本tag。

```bash
# 在154执行，复用本次incoming中的工具
sh "$tool" rollback "$tag" --apply
```

工具要求实际运行的是本候选版本、无活动任务或启用调度、前后schema相同。先对当前数据另做一份冷备份 `backups/tag-rollback-时间/`，再启动 state.json 记录的上一版本，核对回滚前后数据指纹，最后恢复 current。

**回滚只切换应用，不恢复旧数据库、不解包旧数据卷。** 若新版本已产生新数据，这些数据继续保留。schema已变、旧镜像不存在、数据不一致或其他发布已接管时停止，不自动覆盖或删除任何数据。

## 7. 发布记录与异常处理

完成后将脱敏回执选择性保存并提交到 `docs/reviews/<日期-用途>/`：代码提交、tag、镜像ID、上一目录、备份路径、SHA、schema、数据保全与公网验收结果。不要复制 `.env`、认证文件、浏览器存储或完整业务响应。当前发布简表更新在 `deploy/README.md`。记录跳过项；未执行公司接口、真机或模型评估时如实说明。

| 情况 | 处置 |
| --- | --- |
| 打包、上传哈希或build失败 | 停止；旧服务未切换。保留日志，使用新tag/新输出目录重试 |
| 发现活动任务或启用调度 | 在页面按业务要求暂停计划，等待运行结束，再重新检查；不要强杀任务 |
| schema/迁移文件变化 | 普通自动流程停止；按下方迁移分支操作 |
| 备份失败 | 保留现场，脚本尝试恢复旧应用；确认健康后排查磁盘/权限，不能跳过备份 |
| 新服务或数据验证失败 | 自动恢复操作前应用；恢复失败则在其目录启动保留镜像，复用当前卷，核对数据 |
| 公网验证失败 | 保留失败回执，执行应用回滚；不要accept或恢复旧数据库 |
| SSH中断或锁被占用 | 先查容器实际镜像、current、verification/state.json和备份；确认原进程结束后再操作，不能并发强行接管 |
| 激活后产生新记录导致accept指纹不一致 | 停止验收，核实写入来源与数据；回滚工具会保护当前数据。不要篡改原指纹“凑通过” |
| 需要恢复数据库 | 单独停写、保护现库与新数据、验证备份恢复副本并制定对账方案；不属于应用rollback |

数据库迁移分支：审查前后Alembic、数据兼容与回滚代价，准备独立恢复演练和备份，安排停写窗口；按 [MySQL迁移手册](../docs/mysql-migration.md) 与 [平台存储规范](../.trellis/spec/backend/mysql-platform-storage.md) 执行。普通脚本没有跳过schema检查的开关。首次部署还需单独建库、准备认证/秘密配置、核对卷及站点入口，不能凭空创建一套空卷替换现有实例。

## 本地维护与验证

```bash
sh -n deploy/scripts/server_release.sh
.venv/bin/ruff check deploy/scripts tests/deploy
.venv/bin/python -m pytest tests/deploy -q
# 可选：启用测试站点内的真实Chromium验证，不连接154
PYTA_PUBLIC_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/deploy/test_public_verify.py -q
```

服务器Shell测试使用模拟Docker命令，覆盖活动任务/schema拒绝、备份失败恢复、启动失败恢复、缺回执拒绝和保留数据回滚。它证明编排分支，不替代真实服务器演练。首次使用新版本发布工具应复核计划及完整回执，逐阶段执行。

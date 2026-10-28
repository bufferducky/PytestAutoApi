# 154 运行结果阅读与递增编号发布

日期：2026-10-28（Asia/Shanghai）。入口：https://test.ysspace2099.com

## 发布结果
- 应用提交：`8e11bf8cec7d9333fa911cf5c9993f19b6525275`，已推送 master。
- 发布 tag：`20261028-run-readability-8e11bf8`；current 已指向 `/home/ubuntu/pytestautoapi/releases/20261028-run-readability-8e11bf8`。
- 镜像 ID：`sha256:20415122916e79cee3a1ece6500e2bc4767460495d859a1480e0eb80d9238dd8`。
- 上一目录/镜像保留：`/home/ubuntu/pytestautoapi/releases/20261027-frontend-ux-1a3e797`。
- 后端与 MySQL 健康、worker 可用、queued=0、last_error=null；没有新增公司业务运行。
- 公网校验 31 项通过（含八页面 × 三档桌面宽度的 24 组布局），0 warnings；原 Basic Auth 保护保留，入口资源 SHA 与发布包一致。
- 公网运行 API 的11条历史记录均返回字符串编号，编号唯一；业务名称来自冻结快照。原链接/ID、版本、环境和证据保留。

## 数据迁移与恢复验证
本次结构从 `0001_mysql` 升级为 `0002_run_numbers`，按 SOP 专项分支处理，没有绕过普通自动发布的同 schema 限制。
AST 结构审查证明旧表不变，只新增编号映射表和 0002 迁移；所有既有 Alembic 文件保持原 hash。

1. 无活动运行、无 active 调度；停 web 后二次盘点，再停止 backend/MySQL。
2. 冷备份原 MySQL 与附件卷，检查 tar/gzip 可读并核对 SHA-256。
3. 将备份恢复到两个独立临时卷及独立网络，无公开端口，先用旧镜像启动验证原内容可读。
4. 在恢复副本升级 0002，启动新镜像；全部 API 资产/版本/运行内容指纹与停写前一致。
5. 正式库执行同一升级，保留原卷；原内容指纹一致，11条历史补号 #1～#11，编号映射 SHA 与演练完全相同。
6. 新服务健康、公网验收通过后，由标准 accept 核验镜像/清单/数据并原子切换 current。

冷备份目录：`/home/ubuntu/pytestautoapi/backups/20261028-run-readability-8e11bf8`。原 MySQL、附件卷和原发布目录均保留；未上传本地库或合并本地测试数据。
详细计数、归档 SHA、映射 SHA 与四次内容比较结果见 migration.json。

## 验证范围
- 隔离打包：359 passed、14 skipped；真实工作台浏览器流程另1项通过；前端类型/生产构建、Ruff及三组可靠性脚本通过。
- 镜像：非root UID10001、16项契约、650条研究观察、Chromium和隔离HTTP worker执行/重建后证据读取通过。
- 真实 MySQL：在服务器冷备恢复副本上实际完成升级与数据保全核对，并在正式库再次核对；默认测试集的可选MySQL项未运行，不混称为已运行。
- DBX 未配置154连接，全局只读模式阻止新增连接；没有修改其策略。本次数据核对使用现有应用只读API，升级使用Alembic。
- 未新建公司业务运行、未执行真实业务写接口、真机或模型评估。

## 操作记录与回退边界
临时校验脚本读取权限、helper镜像缺少Docker CLI，以及受限备份目录的执行UID问题在正式迁移前修正。备份恢复与升级演练通过后才迁移正式实例。
一次性操作工具保存在服务器 incoming/tag/migration-tools；各文件SHA见 migration.json，公开副本随本文记录，不包含凭证。

普通同schema rollback 不适用于此次0001→0002升级；旧镜像的Store仅接受0001。
回退需先停写，保全升级后新数据并按专项恢复/兼容修复方案操作。不得直接覆盖现库、删除原卷或宣称仅切旧镜像即可无损回退。

## 回执
- manifest.json：提交、产物、工具与入口资源 SHA。
- public.json：公网HTTP/浏览器检查结果。
- public-run-fields.json：公网编号/业务名称字段校验，不包含业务响应正文。
- migration.json：迁移、恢复验证、备份和数据保全摘要，不包含环境配置。

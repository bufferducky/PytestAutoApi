# 运行阅读与编号优化验收

日期：2026-10-28（Asia/Shanghai）。范围：本地工作台与独立离线测试，不触发公司业务运行，不部署服务器。

## 已完成
- 运行摘要/首页显示冻结快照名称，run_number 用字符串返回；原 run_id、链接与复跑关联保持。
- 数据库新增 run_numbers 自增映射，Alembic 0002 为历史补号；本地 MySQL 已升级，三条历史 API 返回 #1/#2/#3。
- 名称与 #编号搜索实点通过；运行列表和详情两行截断，原 ID 可复制。
- 长错误与断言差异默认折叠，显示缺失/多出/重复数量；实点展开可见完整 ID，pre 局部滚动且全页无横向溢出。
- password 回填为中文且下拉正确选中；历史值保留；调度 skip/queue 改中文展示。
- 离开编辑提示、诊断枚举与计数中文化。

## 自动检查
- 全量：`.venv/bin/python -m pytest tests/engine tests/compat tests/backend -q`：310 passed, 11 skipped（浏览器/真实 MySQL 等显式启用项）。
- 最终受影响专项：test_run_numbers.py、test_mysql_migration.py、test_reliable_runs.py：59 passed。
- 前端可靠性、环境未保存保护、环境变量检查均通过；TypeScript/生产构建、变更 Python Ruff 和 git diff --check 通过。
- 新编号测试覆盖两个仓储连接并发、幂等重试、重启读取、outbox 故障整体回滚、旧库缺表补号及重复补号、创建/列表/详情字段一致、名称快照隔离。
- 超过 JavaScript 安全整数的编号按字符串适配，不丢精度。

## 实际页面
`layout.json` 记录 1280/1440/1920 三宽度全页无横向溢出、标题两行 clamp 生效。对应 PNG 是实际本地历史数据截图；environment-auth.png 是鉴权回显检查。

## 发布注意
本地已执行 Alembic upgrade head（0002_run_numbers）。其他环境需在停写时执行同一升级，再启动新版服务；没有隐式启动建表、没有执行远程发布。自增允许空号，不是业务完成顺序。

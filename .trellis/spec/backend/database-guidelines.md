# 旧业务 SQL 工具退役说明

2026-10-27 已移除旧脚本框架中的 `utils/mysql_tool` 与 `common/config.yaml`，原 YAML 业务 SQL 执行规范不再适用。

平台数据库以 [MySQL Platform Storage](./mysql-platform-storage.md) 为准：schema 在 `db/schema.py`，迁移使用 Alembic，仓储使用 Store 事务。YAML 导入的未支持 SQL 字段继续记录为迁移阻塞，不能宣称已经执行 SQL 断言。

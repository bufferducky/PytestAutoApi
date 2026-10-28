# 运行展示编号与名称（2026-10-28）


### 1. Scope / Trigger
修改运行摘要、编号、数据库升级、历史导入及前端运行列表时适用。

### 2. Signatures
`run_numbers(number BIGINT AUTO_INCREMENT PRIMARY KEY, run_id UNIQUE NOT NULL)`；
`CreateRunResponse.run_number: Optional[str]`；`RunSummaryResponse`/详情另含 `name: Optional[str]`。
首页 recent_runs 同样返回 name/run_number。

### 3. Contracts
`run_id` 保留现有关联职责和链接。展示编号单独分配，在 run/outbox 同一写事务内提交；幂等重复返回原编号。
编号允许空号，不表示执行完成顺序，不回收。API 用十进制字符串传递，避免 JavaScript 精度丢失。
名称读取冻结 `payload.run_definition.name`，不读取当前草稿；历史缺失显示“未命名运行”。
升级先停写，运行 Alembic upgrade head；0002 创建编号表并按 created_at/run_id 为历史补号，不改历史记录。
迁移导入使用 0002 schema，并在同一导入事务为新增历史补号。生产仓储启动不隐式升级。

### 4. Validation & Error Matrix
| 场景 | 行为 |
| --- | --- |
| 多连接并发创建 | 编号唯一且后续编号递增 |
| 幂等重试/进程重启/终态回写 | 保持原编号 |
| outbox 写入失败 | run/编号关联/outbox 一并回滚 |
| 历史补号重复执行 | 保持已有编号 |
| API bigint 超过 JS 安全整数 | 字符串不丢精度 |
| schema 未升级 | 明确要求 Alembic upgrade head |

### 5. Good / Base / Bad Cases
Good：业务名称 + #编号，原 ID 可复制；Base：缺名称使用明确空值提示；Bad：分页位置或 MAX+1 充当编号，改名覆盖历史快照。

### 6. Tests Required
`tests/backend/test_run_numbers.py` 验证并发、幂等、重启、事务回滚、历史补号与服务层名称快照。
`tests/backend/test_mysql_migration.py` 验证历史导入；`tests/frontend/reliability.cjs` 验证编号精度与关联 ID 不变。
实际本地 MySQL 升级后通过 API 与浏览器核对历史名称/编号。

### 7. Wrong vs Correct
Wrong：`name = suite_id`，页面用行号作为运行编号。
Correct：`name = payload.run_definition.name`，持久编号由数据库分配，关联和执行仍使用 run_id。

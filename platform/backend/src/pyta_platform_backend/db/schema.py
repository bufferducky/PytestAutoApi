"""平台 schema 的唯一声明；生产升级通过 Alembic，而不是仓储启动建表。"""

from sqlalchemy import JSON, Column, Index, Integer, MetaData, String, Table, Text

metadata = MetaData()
# ID 使用二进制排序，避免 MySQL 默认不区分大小写导致历史 ID 合并。
key = String(191, collation="utf8mb4_bin").with_variant(String(191), "sqlite")
short = String(64)
stamp = String(40)


def table(name, *columns, **kw):
    return Table(name, metadata, *columns, mysql_charset="utf8mb4", **kw)


def ident(name="id", **kw):
    return Column(name, key, **kw)


def document(name="data_json"):
    return Column(name, JSON, nullable=False)


runs = table(
    "runs",
    ident("run_id", primary_key=True),
    ident("suite_id", nullable=False),
    ident("environment_id"),
    Column("environment_name", Text),
    Column("trigger_source", short, nullable=False),
    Column("requested_by", key, nullable=False),
    document("payload_json"),
    Column("status", short, nullable=False),
    Column("created_at", stamp, nullable=False),
    Column("updated_at", stamp, nullable=False),
    Column("started_at", stamp),
    Column("finished_at", stamp),
    Column("status_message", Text),
    document("execution_json"),
)
Index("idx_runs_created_at", runs.c.created_at)
Index("idx_runs_status", runs.c.status, runs.c.created_at)
environments = table(
    "environments",
    ident(primary_key=True),
    Column("name", key, nullable=False),
    Column("base_url", Text, nullable=False),
    Column("auth_mode", Text, nullable=False),
    Column("status", short, nullable=False),
    document("variables_json"),
)
Index("idx_environments_name", environments.c.name)
context_profiles = table(
    "context_profiles",
    ident("kind", primary_key=True),
    ident(primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("deleted", Integer, nullable=False),
    document(),
)
asset_drafts = table(
    "asset_drafts",
    ident("kind", primary_key=True),
    ident(primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("archived", Integer, nullable=False),
    document("draft_json"),
)
asset_versions = table(
    "asset_versions",
    ident("kind", primary_key=True),
    ident(primary_key=True),
    Column("version", Integer, primary_key=True),
    document(),
)
coverage_items = table(
    "coverage_items",
    ident(primary_key=True),
    Column("revision", Integer, nullable=False),
    document(),
)
resource_records = table(
    "resource_records",
    ident(primary_key=True),
    ident("run_id", nullable=False),
    Column("state", short, nullable=False),
    document(),
)
Index("idx_resource_run", resource_records.c.run_id)
resource_pool = table(
    "resource_pool",
    ident(primary_key=True),
    ident("pool_id", nullable=False),
    Column("state", short, nullable=False),
    ident("owner"),
    Column("generation", Integer, nullable=False),
    Column("expires_at", stamp),
    document(),
)
Index("idx_pool_available", resource_pool.c.pool_id, resource_pool.c.state)
resource_audit = table("resource_audit", ident(primary_key=True), ident("run_id"), document())
artifact_refs = table("artifact_refs", ident(primary_key=True), ident("run_id"), document())
Index("idx_artifact_run", artifact_refs.c.run_id)
diagnostic_timing = table("diagnostic_timing", ident(primary_key=True), ident("run_id"), document())
artifact_policy = table("artifact_policy", Column("id", Integer, primary_key=True), document())
schedules = table(
    "schedules",
    ident(primary_key=True),
    Column("revision", Integer, nullable=False),
    document(),
)
schedule_triggers = table(
    "schedule_triggers",
    ident(primary_key=True),
    ident("schedule_id", nullable=False),
    Column("revision", Integer, nullable=False),
    Column("planned_at", stamp, nullable=False),
    Column("state", short, nullable=False),
    document(),
)
Index(
    "uq_schedule_occurrence",
    schedule_triggers.c.schedule_id,
    schedule_triggers.c.revision,
    schedule_triggers.c.planned_at,
    unique=True,
)
release_reports = table("release_reports", ident(primary_key=True), document())
notification_state = table("notification_state", ident("channel", primary_key=True), document())
evaluation_reports = table("evaluation_reports", ident("run_id", primary_key=True), document())
human_reviews = table(
    "human_reviews",
    ident(primary_key=True),
    ident("run_id"),
    ident("sample_id"),
    document(),
)
# 个人工作台写事务短且低频。统一行锁串行化跨仓储/跨进程的读改写，
# 防止租约、修订号、attempt 在两个连接同时读旧值后互相覆盖。
write_guard = table("write_guard", Column("id", Integer, primary_key=True))
run_outbox = table(
    "run_outbox",
    ident("run_id", primary_key=True),
    Column("state", short, nullable=False),
    ident("owner"),
    Column("attempt", Integer, nullable=False),
    Column("lease_until", stamp),
    Column("priority", Integer, nullable=False),
    Column("created_at", stamp, nullable=False),
)
Index("idx_outbox_pending", run_outbox.c.state, run_outbox.c.priority, run_outbox.c.created_at)
migration_ledger = table(
    "migration_ledger",
    ident(primary_key=True),
    Column("source_hash", short, nullable=False),
    document(),
)

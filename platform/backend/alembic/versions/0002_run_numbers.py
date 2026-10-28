"""增加可读运行编号，保留全部历史关联 ID。"""

from alembic import op
from pyta_platform_backend.db.schema import run_numbers, runs, write_guard
from sqlalchemy import select

revision = "0002_run_numbers"
down_revision = "0001_mysql"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # 初次建库的 0001 使用 metadata.create_all，可能已创建此表。
    run_numbers.create(connection, checkfirst=True)
    if connection.dialect.name == "mysql":
        connection.execute(select(write_guard.c.id).with_for_update()).all()
    existing = select(run_numbers.c.run_id)
    # 只排序轻量列，避免 MySQL 对完整证据 JSON 做 filesort。
    records = (
        connection.execute(
            select(runs.c.run_id)
            .where(~runs.c.run_id.in_(existing))
            .order_by(runs.c.created_at, runs.c.run_id)
        )
        .scalars()
        .all()
    )
    for run_id in records:
        connection.execute(run_numbers.insert().values(run_id=run_id))


def downgrade():
    raise RuntimeError("运行编号不可回收；请使用备份和停写回滚流程")

"""平台 MySQL 初始 schema（无演示种子）。"""

from alembic import op
from pyta_platform_backend.db.schema import metadata, write_guard

revision = "0001_mysql"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    metadata.create_all(bind)
    bind.execute(write_guard.insert().values(id=1))


def downgrade():
    raise RuntimeError("不支持自动删除业务表；请按备份与停写回滚流程处理")

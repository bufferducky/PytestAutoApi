"""从应用设置读取连接，不在配置文件中保存数据库口令。"""

from alembic import context
from pyta_platform_backend.config import BackendSettings
from pyta_platform_backend.db.schema import metadata
from sqlalchemy import create_engine

url = BackendSettings.from_env().resolve_database_url()
if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()

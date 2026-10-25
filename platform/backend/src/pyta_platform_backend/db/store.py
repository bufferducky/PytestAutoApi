"""短连接 SQLAlchemy 单元：方言由驱动处理，仓储不持有跨线程 DBAPI 连接。"""

import json
from contextlib import contextmanager
from pathlib import Path
from threading import RLock, local

from sqlalchemy import JSON, create_engine, inspect, select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.pool import StaticPool

from pyta_platform_backend.db.schema import metadata, write_guard

_engines = {}
_engine_lock = RLock()


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, result):
        self.rowcount = result.rowcount
        self.rows = [Row(row._mapping) for row in result.fetchall()] if result.returns_rows else []

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def __iter__(self):
        return iter(self.rows)


def engine_for(location):
    """裸 SQLite 路径仅供显式构造的离线测试仓储；应用设置禁止生产使用。"""
    location = str(location)
    if "://" not in location:
        location = (
            "sqlite+pysqlite://"
            if location == ":memory:"
            else ("sqlite+pysqlite:///" + str(Path(location).resolve()))
        )
    with _engine_lock:
        if location not in _engines:
            kwargs = {"pool_pre_ping": True}
            if location.startswith("sqlite"):
                kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
                if location == "sqlite+pysqlite://":
                    # 每个显式内存仓储默认隔离；应用测试通过唯一文件共享同一次装配。
                    return create_engine(location, poolclass=StaticPool, **kwargs)
            _engines[location] = create_engine(location, **kwargs)
        return _engines[location]


class Store:
    def __init__(self, location):
        self.engine = engine_for(location)
        self._local = local()
        self._lock = RLock()
        if self.engine.dialect.name == "sqlite":
            metadata.create_all(self.engine)
            with self.engine.begin() as conn:
                conn.execute(sqlite_insert(write_guard).values(id=1).on_conflict_do_nothing())
        else:
            with self.engine.connect() as conn:
                if not inspect(conn).has_table("alembic_version"):
                    raise RuntimeError("MySQL schema 未升级，请先执行 Alembic upgrade head")
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if revision != "0001_mysql":
                    raise RuntimeError("MySQL schema 版本不兼容，请先执行 Alembic upgrade head")

    @property
    def in_transaction(self):
        return getattr(self._local, "connection", None) is not None

    def begin(self):
        if self.in_transaction:
            raise RuntimeError("重复开启存储事务")
        self._lock.acquire()
        conn = None
        try:
            conn = self.engine.connect()
            if self.engine.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
                conn.execute(
                    select(write_guard.c.id).where(write_guard.c.id == 1).with_for_update()
                ).scalar_one()
            self._local.connection = conn
        except BaseException:
            if conn is not None:
                conn.close()
            self._lock.release()
            raise

    def _end(self, commit):
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            try:
                conn.commit() if commit else conn.rollback()
            finally:
                self._local.connection = None
                conn.close()
                self._lock.release()

    def commit(self):
        self._end(True)

    def rollback(self):
        self._end(False)

    @contextmanager
    def transaction(self):
        nested = self.in_transaction
        if not nested:
            self.begin()
        try:
            yield
            if not nested:
                self.commit()
        except BaseException:
            if not nested:
                self.rollback()
            raise

    def execute(self, statement, parameters=()):
        # 只把位置参数转成 SQLAlchemy bind；不改写 SQL 方言或吞掉数据库错误。
        if isinstance(statement, str):
            if not isinstance(parameters, dict):
                parts = statement.split("?")
                if len(parts) != len(parameters) + 1:
                    raise ValueError("SQL bind 数量不匹配")
                statement = "".join(
                    part + (f":p{i}" if i < len(parameters) else "") for i, part in enumerate(parts)
                )
                parameters = {f"p{i}": value for i, value in enumerate(parameters)}
            statement = text(statement)
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            return Result(conn.execute(statement, parameters or {}))
        with self.engine.begin() as conn:
            return Result(conn.execute(statement, parameters or {}))

    def upsert(self, table_name, values, update=None, *, ignore=False):
        table = metadata.tables[table_name]
        values = {
            k: json.loads(v) if isinstance(table.c[k].type, JSON) and isinstance(v, str) else v
            for k, v in values.items()
        }
        insert = mysql_insert if self.engine.dialect.name == "mysql" else sqlite_insert
        statement = insert(table).values(**values)
        columns = update if update is not None else list(values)
        if self.engine.dialect.name == "mysql":
            changes = {k: statement.inserted[k] for k in columns}
            if ignore:
                pk = list(table.primary_key)[0].name
                changes = {pk: table.c[pk]}
            statement = statement.on_duplicate_key_update(**changes)
        elif ignore:
            statement = statement.on_conflict_do_nothing()
        else:
            statement = statement.on_conflict_do_update(
                index_elements=list(table.primary_key),
                set_={k: statement.excluded[k] for k in columns},
            )
        return self.execute(statement)

    def close(self):
        self.rollback()

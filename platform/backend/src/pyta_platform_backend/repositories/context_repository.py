"""配置修订历史。公开快照自包含，执行不回查正在编辑的配置。"""

from threading import RLock

from pyta_platform_backend.db.store import Store
from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.repositories.sqlite_support import dump_json, load_json


class ContextRepository:
    def __init__(self, database_path):
        self._lock = RLock()
        self._connection = Store(database_path)

    def list(self, kind):
        with self._lock:
            rows = self._connection.execute(
                """SELECT c.* FROM context_profiles c
                JOIN (SELECT id,max(revision) revision FROM context_profiles
                    WHERE kind=? GROUP BY id) latest
                ON c.id=latest.id AND c.revision=latest.revision
                WHERE c.kind=? AND c.deleted=0 ORDER BY c.id""",
                (kind, kind),
            ).fetchall()
            return [load_json(row["data_json"], {}) for row in rows]

    def exists(self, kind, identifier):
        with self._lock:
            return (
                self._connection.execute(
                    "SELECT 1 FROM context_profiles WHERE kind=? AND id=? LIMIT 1",
                    (kind, identifier),
                ).fetchone()
                is not None
            )

    def get(self, kind, identifier):
        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM context_profiles
                WHERE kind=? AND id=? ORDER BY revision DESC LIMIT 1""",
                (kind, identifier),
            ).fetchone()
            if row is None or row["deleted"]:
                raise KeyError(f"{kind} 不存在: {identifier}")
            return load_json(row["data_json"], {})

    def save(self, kind, data, *, creating=False, deleting=False):
        with self._lock:
            self._connection.begin()
            try:
                row = self._connection.execute(
                    """SELECT * FROM context_profiles
                    WHERE kind=? AND id=? ORDER BY revision DESC LIMIT 1""",
                    (kind, data["id"]),
                ).fetchone()
                if creating:
                    if row is not None:
                        raise RunConflict("配置 ID 已存在；删除的 ID 不能重新解释历史")
                    data = {**data, "revision": 1}
                else:
                    if row is None or row["deleted"]:
                        raise KeyError(f"{kind} 不存在: {data['id']}")
                    if row["revision"] != data["revision"]:
                        raise RunConflict("配置已更新，请刷新后重试")
                    data = {**data, "revision": row["revision"] + 1}
                self._connection.execute(
                    "INSERT INTO context_profiles VALUES (?,?,?,?,?)",
                    (
                        kind,
                        data["id"],
                        data["revision"],
                        int(deleting),
                        dump_json(data),
                    ),
                )
                self._connection.commit()
                return data
            except BaseException:
                self._connection.rollback()
                raise

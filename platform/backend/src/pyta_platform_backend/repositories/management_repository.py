"""真实资产目录与环境持久化；常规启动不写演示种子。"""

from dataclasses import dataclass
from threading import RLock
from typing import Optional
from uuid import uuid4

from pyta_platform_backend.db.store import Store
from pyta_platform_backend.repositories.sqlite_support import dump_json, load_json


@dataclass(frozen=True)
class CaseRecord:
    """用例目录记录。"""

    id: str
    name: str
    module: str
    method: str
    priority: str
    status: str


@dataclass(frozen=True)
class SuiteRecord:
    """套件目录记录。"""

    id: str
    name: str
    case_count: int
    schedule: str


@dataclass(frozen=True)
class EnvironmentRecord:
    """环境目录记录。"""

    id: str
    name: str
    base_url: str
    auth_mode: str
    status: str
    variables: dict[str, object]


@dataclass(frozen=True)
class ScheduleRecord:
    """调度目录记录。"""

    id: str
    name: str
    cron: str
    target_suite_id: str
    environment_id: str
    status: str


class InMemoryManagementRepository:
    """显式测试用内存仓储，不预置任何演示记录。"""

    def __init__(self):
        self._cases, self._suites, self._schedules = [], [], []
        self._environments = {}

    def list_cases(self) -> list[CaseRecord]:
        """列出当前可展示的用例目录。"""

        return list(self._cases)

    def list_suites(self) -> list[SuiteRecord]:
        """列出当前可展示的套件目录。"""

        return list(self._suites)

    def list_environments(self) -> list[EnvironmentRecord]:
        """列出环境目录。"""

        return list(self._environments.values())

    def get_environment_by_id(self, environment_id: str) -> Optional[EnvironmentRecord]:
        """按 id 读取环境。"""

        return self._environments.get(environment_id)

    def create_environment(
        self,
        *,
        name: str,
        base_url: str,
        auth_mode: str,
        status: str,
        variables: dict[str, object],
    ) -> Optional[EnvironmentRecord]:
        """创建新的环境目录记录。"""

        normalized_name = name.strip().lower()
        if any(
            item.name.strip().lower() == normalized_name for item in self._environments.values()
        ):
            raise ValueError(f"环境名称已存在: {name}")

        record = EnvironmentRecord(
            id=uuid4().hex,
            name=name,
            base_url=base_url,
            auth_mode=auth_mode,
            status=status,
            variables=dict(variables),
        )
        self._environments[record.id] = record
        return record

    def update_environment(
        self,
        environment_id: str,
        *,
        name: str,
        base_url: str,
        auth_mode: str,
        status: str,
        variables: dict[str, object],
    ) -> Optional[EnvironmentRecord]:
        """更新环境目录记录。"""

        existing = self.get_environment_by_id(environment_id)
        if existing is None:
            return None

        normalized_name = name.strip().lower()
        if any(
            item.id != environment_id and item.name.strip().lower() == normalized_name
            for item in self._environments.values()
        ):
            raise ValueError(f"环境名称已存在: {name}")

        updated = EnvironmentRecord(
            id=existing.id,
            name=name,
            base_url=base_url,
            auth_mode=auth_mode,
            status=status,
            variables=dict(variables),
        )
        self._environments[environment_id] = updated
        return updated

    def delete_environment(self, environment_id: str) -> Optional[EnvironmentRecord]:
        """删除环境目录记录。"""

        return self._environments.pop(environment_id, None)

    def list_schedules(self) -> list[ScheduleRecord]:
        """列出调度目录。"""

        return list(self._schedules)


class SqlManagementRepository(InMemoryManagementRepository):
    """管理目录从版本化资产/调度读取；环境为真实可编辑配置。"""

    def __init__(self, database_path):
        self._database_path = database_path
        self._connection = Store(database_path)
        self._lock = RLock()

    def _assets(self, kind):
        return self._connection.execute(
            "SELECT id,draft_json,archived FROM asset_drafts "
            "WHERE kind=? AND archived=0 ORDER BY id",
            (kind,),
        ).fetchall()

    def list_cases(self):
        records = []
        for row in self._assets("scenarios"):
            draft = load_json(row["draft_json"], {})
            steps = draft.get("steps", [])
            request = steps[0].get("request", {}) if steps else {}
            records.append(
                CaseRecord(
                    id=row["id"],
                    name=draft.get("name", row["id"]),
                    module=draft.get("module", "未分类"),
                    method=request.get("method", "GET"),
                    priority=draft.get("priority", "P1"),
                    status="active" if self._published("scenarios", row["id"]) else "draft",
                )
            )
        return records

    def _published(self, kind, identifier):
        return bool(
            self._connection.execute(
                "SELECT 1 FROM asset_versions WHERE kind=? AND id=? LIMIT 1",
                (kind, identifier),
            ).fetchone()
        )

    def list_suites(self):
        schedules = self.list_schedules()
        records = []
        for row in self._assets("suites"):
            draft = load_json(row["draft_json"], {})
            records.append(
                SuiteRecord(
                    id=row["id"],
                    name=draft.get("name", row["id"]),
                    case_count=len(draft.get("scenarios", [])),
                    schedule="、".join(x.cron for x in schedules if x.target_suite_id == row["id"]),
                )
            )
        return records

    def list_schedules(self):
        records = []
        for row in self._connection.execute("SELECT data_json FROM schedules ORDER BY id"):
            data = load_json(row[0], {})
            records.append(
                ScheduleRecord(
                    id=data["id"],
                    name=data.get("name", data["id"]),
                    cron=data.get("cron", ""),
                    target_suite_id=data.get("suite_id", ""),
                    environment_id=data.get("environment_id") or "",
                    status=data.get("status", "paused"),
                )
            )
        return records

    def list_environments(self) -> list[EnvironmentRecord]:
        """列出环境目录。"""

        rows = self._connection.execute(
            """
            SELECT id, name, base_url, auth_mode, status, variables_json
            FROM environments
            ORDER BY id ASC
            """
        ).fetchall()

        return [self._row_to_environment(row) for row in rows]

    def get_environment_by_id(self, environment_id: str) -> Optional[EnvironmentRecord]:
        """按 id 读取环境。"""

        row = self._connection.execute(
            """
            SELECT id, name, base_url, auth_mode, status, variables_json
            FROM environments
            WHERE id = ?
            """,
            (environment_id,),
        ).fetchone()

        if row is None:
            return None
        return self._row_to_environment(row)

    def create_environment(
        self,
        *,
        name: str,
        base_url: str,
        auth_mode: str,
        status: str,
        variables: dict[str, object],
    ) -> Optional[EnvironmentRecord]:
        """创建新的环境目录记录。"""

        with self._lock, self._connection.transaction():
            normalized_name = name.strip().lower()
            if self._name_exists(self._connection, normalized_name):
                raise ValueError(f"环境名称已存在: {name}")

            record = EnvironmentRecord(
                id=uuid4().hex,
                name=name,
                base_url=base_url,
                auth_mode=auth_mode,
                status=status,
                variables=dict(variables),
            )
            self._connection.execute(
                """
                INSERT INTO environments (
                    id,
                    name,
                    base_url,
                    auth_mode,
                    status,
                    variables_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.name,
                    record.base_url,
                    record.auth_mode,
                    record.status,
                    dump_json(record.variables),
                ),
            )

            return record

    def update_environment(
        self,
        environment_id: str,
        *,
        name: str,
        base_url: str,
        auth_mode: str,
        status: str,
        variables: dict[str, object],
    ) -> Optional[EnvironmentRecord]:
        """更新环境目录记录。"""

        with self._lock, self._connection.transaction():
            existing = self._connection.execute(
                """
                SELECT id, name, base_url, auth_mode, status, variables_json
                FROM environments
                WHERE id = ?
                """,
                (environment_id,),
            ).fetchone()
            if existing is None:
                return None

            normalized_name = name.strip().lower()
            if self._name_exists(self._connection, normalized_name, exclude_id=environment_id):
                raise ValueError(f"环境名称已存在: {name}")

            updated = EnvironmentRecord(
                id=environment_id,
                name=name,
                base_url=base_url,
                auth_mode=auth_mode,
                status=status,
                variables=dict(variables),
            )
            self._connection.execute(
                """
                UPDATE environments
                SET
                    name = ?,
                    base_url = ?,
                    auth_mode = ?,
                    status = ?,
                    variables_json = ?
                WHERE id = ?
                """,
                (
                    updated.name,
                    updated.base_url,
                    updated.auth_mode,
                    updated.status,
                    dump_json(updated.variables),
                    updated.id,
                ),
            )

            return updated

    def delete_environment(self, environment_id: str) -> Optional[EnvironmentRecord]:
        """删除环境目录记录。"""

        with self._lock, self._connection.transaction():
            row = self._connection.execute(
                """
                SELECT id, name, base_url, auth_mode, status, variables_json
                FROM environments
                WHERE id = ?
                """,
                (environment_id,),
            ).fetchone()
            if row is None:
                return None

            self._connection.execute(
                "DELETE FROM environments WHERE id = ?",
                (environment_id,),
            )

            return self._row_to_environment(row)

    @staticmethod
    def _name_exists(connection, normalized_name: str, exclude_id: Optional[str] = None) -> bool:
        """检查环境名称是否已存在。"""

        row = connection.execute(
            "SELECT id, name FROM environments",
        ).fetchall()
        for item in row:
            if exclude_id and item["id"] == exclude_id:
                continue
            if str(item["name"]).strip().lower() == normalized_name:
                return True
        return False

    @staticmethod
    def _row_to_environment(row) -> EnvironmentRecord:
        """把数据库行还原为 EnvironmentRecord。"""

        return EnvironmentRecord(
            id=row["id"],
            name=row["name"],
            base_url=row["base_url"],
            auth_mode=row["auth_mode"],
            status=row["status"],
            variables=load_json(row["variables_json"], default={}),
        )


SqliteManagementRepository = SqlManagementRepository

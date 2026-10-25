"""资源所有权、租约和清理事实。过期只进入待对账，不能立即转给下一run。"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from pyta_platform_backend.repositories.asset_repository import AssetRepository, asset_hash
from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.repositories.sqlite_support import dump_json, load_json


def now():
    return datetime.now(timezone.utc)


class ResourceRepository(AssetRepository):
    def __init__(self, path):
        super().__init__(path)

    def define(self, kind, data):
        identifier = data.pop("id", None) or uuid4().hex
        with self.transaction():
            version = self._connection.execute(
                "SELECT coalesce(max(version),0)+1 FROM asset_versions WHERE kind=? AND id=?",
                (kind, identifier),
            ).fetchone()[0]
            result = {"id": identifier, "version": version, "hash": asset_hash(data), "data": data}
            self._connection.execute(
                "INSERT INTO asset_versions VALUES (?,?,?,?)",
                (kind, identifier, version, dump_json(result)),
            )
        return result

    def definitions(self, kind):
        with self._lock:
            rows = self._connection.execute(
                "SELECT data_json FROM asset_versions WHERE kind=? ORDER BY id,version DESC",
                (kind,),
            ).fetchall()
            return [load_json(row[0], {}) for row in rows]

    def add_pool(self, data):
        if not data["dedicated_test_resource"]:
            raise ValueError("资源池只接收明确专属测试资源")
        key = asset_hash(
            {k: data[k] for k in ["target_id", "tenant_id", "project_id", "object_id"]}
        )
        with self.transaction():
            try:
                self._connection.execute(
                    "INSERT INTO resource_pool VALUES (?,?,?,NULL,0,NULL,?)",
                    (key, data["pool_id"], "available", dump_json(data)),
                )
            except IntegrityError as exc:
                raise RunConflict("对象已在资源池，不能以另一个pool重复注册") from exc
        return {"id": key, **data, "state": "available"}

    def pool(self):
        self.expire_leases()
        with self._lock:
            return [
                {**load_json(row["data_json"], {}), **dict(row)}
                for row in self._connection.execute("SELECT * FROM resource_pool").fetchall()
            ]

    def expire_leases(self):
        with self.transaction():
            self._connection.execute(
                """UPDATE resource_pool SET state='needs_reconciliation'
                WHERE state='leased' AND expires_at<=?""",
                (now().isoformat(),),
            )

    def lease(self, pool_id, owner, context, seconds, object_id=None):
        self.expire_leases()
        with self.transaction():
            rows = self._connection.execute(
                "SELECT * FROM resource_pool WHERE pool_id=? AND state='available'", (pool_id,)
            ).fetchall()
            selected = next(
                (
                    row
                    for row in rows
                    if (
                        object_id is None
                        or load_json(row["data_json"], {}).get("object_id") == object_id
                    )
                    and all(
                        load_json(row["data_json"], {}).get(k) == context[k]
                        for k in ["target_id", "tenant_id", "project_id"]
                    )
                ),
                None,
            )
            if selected is None:
                raise RunConflict("没有可用且归属匹配的专属池资源")
            expires = (now() + timedelta(seconds=seconds)).isoformat()
            generation = selected["generation"] + 1
            self._connection.execute(
                """UPDATE resource_pool SET state='leased',owner=?,generation=?,expires_at=?
                    WHERE id=?""",
                (owner, generation, expires, selected["id"]),
            )
            return {
                "pool_resource_id": selected["id"],
                "owner": owner,
                "generation": generation,
                "expires_at": expires,
                "object_id": load_json(selected["data_json"], {})["object_id"],
            }

    def check_lease(self, lease):
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM resource_pool WHERE id=?", (lease["pool_resource_id"],)
            ).fetchone()
            if (
                row is None
                or row["owner"] != lease["owner"]
                or row["generation"] != lease["generation"]
            ):
                raise RunConflict("租约owner/generation不匹配")
            if row["state"] != "leased" or datetime.fromisoformat(row["expires_at"]) <= now():
                raise RunConflict("租约已失效，停止新操作并对账")
            return dict(row)

    def renew(self, lease, seconds):
        with self.transaction():
            self.check_lease(lease)
            expires = (now() + timedelta(seconds=seconds)).isoformat()
            self._connection.execute(
                "UPDATE resource_pool SET expires_at=? WHERE id=?",
                (expires, lease["pool_resource_id"]),
            )
            return {**lease, "expires_at": expires}

    def release_lease(self, lease):
        with self.transaction():
            row = self._connection.execute(
                "SELECT * FROM resource_pool WHERE id=?", (lease["pool_resource_id"],)
            ).fetchone()
            if (
                row is None
                or row["owner"] != lease["owner"]
                or row["generation"] != lease["generation"]
            ):
                raise RunConflict("旧owner不能释放其他run的租约")
            self._connection.execute(
                "UPDATE resource_pool SET state='available',owner=NULL,expires_at=NULL WHERE id=?",
                (row["id"],),
            )

    def put_resource(self, data):
        with self.transaction():
            self._connection.upsert(
                "resource_records",
                {
                    "id": data["id"],
                    "run_id": data["run_id"],
                    "state": data["state"],
                    "data_json": dump_json(data),
                },
                update=["state", "data_json"],
            )
        return data

    def resources(self, run_id=None):
        with self._lock:
            rows = self._connection.execute(
                "SELECT data_json FROM resource_records"
                + (" WHERE run_id=?" if run_id else "")
                + " ORDER BY id",
                (run_id,) if run_id else (),
            ).fetchall()
            return [load_json(row[0], {}) for row in rows]

    def reconcile(self, active_run_ids):
        with self.transaction():
            for row in self._connection.execute("SELECT * FROM resource_records").fetchall():
                data = load_json(row["data_json"], {})
                if row["run_id"] not in active_run_ids and row["state"] in {
                    "acquiring",
                    "acquired",
                    "in_use",
                    "releasing",
                }:
                    data["state"] = (
                        "ownership_unknown"
                        if row["state"] == "acquiring" and not data.get("object_id")
                        else "needs_reconciliation"
                    )
                    if data.get("lease"):
                        lease = data["lease"]
                        self._connection.execute(
                            """UPDATE resource_pool SET state='needs_reconciliation'
                            WHERE id=? AND owner=? AND generation=?""",
                            (lease["pool_resource_id"], lease["owner"], lease["generation"]),
                        )
                    self._connection.execute(
                        "UPDATE resource_records SET state=?,data_json=? WHERE id=?",
                        (data["state"], dump_json(data), row["id"]),
                    )

    def audit(self, run_id, action, details):
        data = {"at": now().isoformat(), "action": action, "details": details}
        with self.transaction():
            self._connection.execute(
                "INSERT INTO resource_audit VALUES (?,?,?)", (uuid4().hex, run_id, dump_json(data))
            )
        return data

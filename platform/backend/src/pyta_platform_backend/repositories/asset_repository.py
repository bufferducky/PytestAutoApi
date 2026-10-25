"""草稿可修改，发布版本只能追加；同事务校验草稿 revision。"""

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from pyta_platform_backend.db.store import Store
from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.repositories.sqlite_support import dump_json, load_json


def asset_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class AssetRepository:
    def __init__(self, path):
        self._database_path = path
        self._lock, self._connection = RLock(), Store(path)

    @contextmanager
    def transaction(self):
        with self._lock, self._connection.transaction():
            yield

    def list(self, kind, offset=0, limit=100):
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM asset_drafts
                WHERE kind=? AND archived=0 ORDER BY id LIMIT ? OFFSET ?""",
                (kind, limit, offset),
            ).fetchall()
            return [self._draft(row) for row in rows]

    def get(self, kind, identifier):
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM asset_drafts WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
            if row is None:
                raise KeyError(f"{kind} 不存在: {identifier}")
            return self._draft(row)

    @staticmethod
    def _draft(row):
        return {
            "id": row["id"],
            "revision": row["revision"],
            "archived": bool(row["archived"]),
            "draft": load_json(row["draft_json"], {}),
        }

    def create(self, kind, data, identifier=None):
        identifier = identifier or uuid4().hex
        with self.transaction():
            try:
                self._connection.execute(
                    "INSERT INTO asset_drafts VALUES (?,?,1,0,?)",
                    (kind, identifier, dump_json(data)),
                )
            except IntegrityError as exc:
                raise RunConflict("资产 ID 已存在") from exc
        return self.get(kind, identifier)

    def update(self, kind, identifier, expected_revision, data, *, archive=False):
        with self.transaction():
            row = self._connection.execute(
                """UPDATE asset_drafts SET revision=revision+1,
                draft_json=?,archived=? WHERE kind=? AND id=? AND revision=? AND archived=0""",
                (dump_json(data), int(archive), kind, identifier, expected_revision),
            )
            if row.rowcount != 1:
                raise RunConflict("草稿已变化/归档，请刷新")
        return self.get(kind, identifier)

    def publish(self, kind, identifier, expected_revision, compiled_data, note, author):
        with self.transaction():
            draft = self.get(kind, identifier)
            if draft["archived"] or draft["revision"] != expected_revision:
                raise RunConflict("草稿已变化/归档，发布取消")
            if asset_hash(draft["draft"]) != asset_hash(compiled_data):
                raise RunConflict("编译数据与草稿修订不一致")
            version = self._connection.execute(
                "SELECT coalesce(max(version),0)+1 FROM asset_versions WHERE kind=? AND id=?",
                (kind, identifier),
            ).fetchone()[0]
            published = {
                "schema_version": 1,
                "id": identifier,
                "version": version,
                "hash": asset_hash(compiled_data),
                "published_at": datetime.now(timezone.utc).isoformat(),
                "author": author,
                "change_note": note,
                "data": compiled_data,
            }
            self._connection.execute(
                "INSERT INTO asset_versions VALUES (?,?,?,?)",
                (kind, identifier, version, dump_json(published)),
            )
        return published

    def version(self, kind, identifier, version):
        with self._lock:
            row = self._connection.execute(
                "SELECT data_json FROM asset_versions WHERE kind=? AND id=? AND version=?",
                (kind, identifier, version),
            ).fetchone()
            if row is None:
                raise KeyError(f"发布版本不存在: {kind}/{identifier}/{version}")
            return load_json(row[0], {})

    def versions(self, kind, identifier):
        with self._lock:
            rows = self._connection.execute(
                "SELECT data_json FROM asset_versions WHERE kind=? AND id=? ORDER BY version DESC",
                (kind, identifier),
            ).fetchall()
            return [load_json(row[0], {}) for row in rows]

    def coverage(self):
        with self._lock:
            return [
                load_json(row[0], {})
                for row in self._connection.execute(
                    "SELECT data_json FROM coverage_items"
                ).fetchall()
            ]

    def save_coverage(self, data, expected_revision=None):
        with self.transaction():
            row = self._connection.execute(
                "SELECT revision FROM coverage_items WHERE id=?", (data["id"],)
            ).fetchone()
            if row and expected_revision is None:
                return False  # 研究导入幂等，不覆盖人工确认。
            if row and row[0] != expected_revision:
                raise RunConflict("覆盖项已更新")
            data = {**data, "revision": row[0] + 1 if row else 1}
            self._connection.upsert(
                "coverage_items",
                {"id": data["id"], "revision": data["revision"], "data_json": dump_json(data)},
                update=["revision", "data_json"],
            )
            return data

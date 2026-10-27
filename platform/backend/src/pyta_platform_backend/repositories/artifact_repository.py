"""受控附件索引与原子文件提交；不接受调用方的任意文件路径。"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from pyta_platform_backend.repositories.asset_repository import AssetRepository
from pyta_platform_backend.repositories.serialization import dump_json, load_json


class ArtifactRepository(AssetRepository):
    def __init__(self, path, root):
        super().__init__(path)
        self.root = Path(root).resolve()
        with self.transaction():
            self._connection.upsert(
                "artifact_policy",
                {
                    "id": 1,
                    "data_json": {
                        "metadata_days": 90,
                        "attachment_days": 14,
                        "failure_attachment_days": 30,
                    },
                },
                ignore=True,
            )

    def add(self, run_id, step_id, content, content_type, redaction_status, retention_days):
        identifier = uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        meta = {
            "artifact_id": identifier,
            "run_id": run_id,
            "step_id": step_id,
            "content_type": content_type,
            "sha256": hashlib.sha256(content).hexdigest(),
            "byte_size": len(content),
            "redaction_status": redaction_status,
            "availability": "available",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=retention_days)).isoformat(),
            "pinned": False,
        }
        temp = self.root / (identifier + ".tmp")
        final = self.root / identifier
        try:
            with temp.open("xb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            temp.replace(final)
            with self.transaction():
                self._connection.execute(
                    "INSERT INTO artifact_refs VALUES (?,?,?)",
                    (identifier, run_id, dump_json(meta)),
                )
        except BaseException:
            temp.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise
        return meta

    def list(self, run_id):
        with self._lock:
            return [
                load_json(row[0], {})
                for row in self._connection.execute(
                    "SELECT data_json FROM artifact_refs WHERE run_id=?", (run_id,)
                ).fetchall()
            ]

    def all_artifacts(self):
        with self._lock:
            return [
                load_json(row[0], {})
                for row in self._connection.execute(
                    "SELECT data_json FROM artifact_refs"
                ).fetchall()
            ]

    def get_artifact(self, identifier):
        with self._lock:
            row = self._connection.execute(
                "SELECT data_json FROM artifact_refs WHERE id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise KeyError("artifact不存在")
            return load_json(row[0], {})

    def update(self, meta):
        with self.transaction():
            self._connection.execute(
                "UPDATE artifact_refs SET data_json=? WHERE id=?",
                (dump_json(meta), meta["artifact_id"]),
            )
        return meta

    def content(self, meta):
        identifier = meta["artifact_id"]
        if (
            not isinstance(identifier, str)
            or len(identifier) != 32
            or any(c not in "0123456789abcdef" for c in identifier)
        ):
            raise ValueError("非法附件ID")
        path = self.root / identifier
        if not path.is_file():
            self.update({**meta, "availability": "missing"})
            raise FileNotFoundError("附件文件缺失")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            self.update({**meta, "availability": "corrupt"})
            raise ValueError("附件完整性损坏")
        return data

    def expire(self, meta):
        # 最终存储边界保护历史，不能通过直接调用绕过 service 保留策略。
        current = self.get_artifact(meta["artifact_id"])
        run = self._connection.execute(
            "SELECT execution_json FROM runs WHERE run_id=?",
            (current["run_id"],),
        ).fetchone()
        if current.get("migration") or (run and load_json(run[0], {}).get("migration")):
            raise ValueError("迁入历史附件受保护，不能回收")
        # 只删除本仓储生成的受控ID文件，不按用户传入路径操作。
        self.content(meta)
        (self.root / meta["artifact_id"]).unlink()
        return self.update({**meta, "availability": "expired"})

    def timing(self, run_id, opened_at, summary_at, scope):
        start = datetime.fromisoformat(opened_at)
        end = datetime.fromisoformat(summary_at)
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError("定位计时须含时区且顺序正确")
        result = {
            "id": uuid4().hex,
            "run_id": run_id,
            "opened_at": opened_at,
            "summary_at": summary_at,
            "seconds": (end - start).total_seconds(),
            "scope": scope,
        }
        with self.transaction():
            self._connection.execute(
                "INSERT INTO diagnostic_timing VALUES (?,?,?)",
                (result["id"], run_id, dump_json(result)),
            )
        return result

    def policy(self):
        with self._lock:
            return load_json(
                self._connection.execute(
                    "SELECT data_json FROM artifact_policy WHERE id=1"
                ).fetchone()[0],
                {},
            )

    def set_policy(self, values):
        if set(values) != {"metadata_days", "attachment_days", "failure_attachment_days"} or any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3650
            for value in values.values()
        ):
            raise ValueError("保留策略必须为三个1—3650天的整数")
        with self.transaction():
            self._connection.execute(
                "UPDATE artifact_policy SET data_json=? WHERE id=1", (dump_json(values),)
            )
        return values

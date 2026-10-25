"""持久outbox + 唯一occurrence；run创建以稳定幂等键恢复。"""

from uuid import uuid4

from pyta_platform_backend.repositories.asset_repository import AssetRepository, asset_hash
from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.repositories.sqlite_support import dump_json, load_json


class ScheduleRepository(AssetRepository):
    def __init__(self, path):
        super().__init__(path)

    def schedules(self):
        with self._lock:
            return [
                load_json(r[0], {})
                for r in self._connection.execute(
                    "SELECT data_json FROM schedules ORDER BY id"
                ).fetchall()
            ]

    def schedule(self, identifier):
        with self._lock:
            row = self._connection.execute(
                "SELECT data_json FROM schedules WHERE id=?", (identifier,)
            ).fetchone()
            if not row:
                raise KeyError("schedule不存在")
            return load_json(row[0], {})

    def save_schedule(self, data, expected_revision=None):
        with self.transaction():
            row = self._connection.execute(
                "SELECT revision FROM schedules WHERE id=?", (data["id"],)
            ).fetchone()
            if row and row[0] != expected_revision:
                raise RunConflict("计划已修改，请刷新")
            if not row and expected_revision is not None:
                raise KeyError("schedule不存在")
            data = {**data, "revision": row[0] + 1 if row else 1}
            self._connection.upsert(
                "schedules",
                {
                    "id": data["id"],
                    "revision": data["revision"],
                    "data_json": dump_json(data),
                },
                update=["revision", "data_json"],
            )
        return data

    def advance(self, identifier, revision, next_fire_at):
        with self.transaction():
            data = self.schedule(identifier)
            if data["revision"] != revision or data["status"] != "active":
                return
            data["next_fire_at"] = next_fire_at
            self._connection.execute(
                "UPDATE schedules SET data_json=? WHERE id=?", (dump_json(data), identifier)
            )

    def trigger(self, schedule, planned_at, state, payload, message=None):
        identifier = asset_hash(
            {
                "schedule_id": schedule["id"],
                "revision": schedule["revision"],
                "planned_at": planned_at,
            }
        )[:32]
        with self.transaction():
            current = self.schedule(schedule["id"])
            if current["revision"] != schedule["revision"] or current["status"] != "active":
                return None
            data = {
                "id": identifier,
                "schedule_id": schedule["id"],
                "schedule_revision": schedule["revision"],
                "planned_at": planned_at,
                "fired_at": None,
                "state": state,
                "run_id": None,
                "payload": payload,
                "message": message,
            }
            self._connection.upsert(
                "schedule_triggers",
                {
                    "id": identifier,
                    "schedule_id": schedule["id"],
                    "revision": schedule["revision"],
                    "planned_at": planned_at,
                    "state": state,
                    "data_json": dump_json(data),
                },
                ignore=True,
            )
            row = self._connection.execute(
                "SELECT data_json FROM schedule_triggers WHERE id=?", (identifier,)
            ).fetchone()
            return load_json(row[0], {})

    def triggers(self, schedule_id=None):
        with self._lock:
            return [
                load_json(row[0], {})
                for row in self._connection.execute(
                    "SELECT data_json FROM schedule_triggers"
                    + (" WHERE schedule_id=?" if schedule_id else "")
                    + " ORDER BY id",
                    (schedule_id,) if schedule_id else (),
                ).fetchall()
            ]

    def set_trigger(self, data):
        with self.transaction():
            self._connection.execute(
                "UPDATE schedule_triggers SET state=?,data_json=? WHERE id=?",
                (data["state"], dump_json(data), data["id"]),
            )
        return data

    def report(self, data):
        identifier = uuid4().hex
        data = {"id": identifier, **data}
        with self.transaction():
            self._connection.execute(
                "INSERT INTO release_reports VALUES (?,?)", (identifier, dump_json(data))
            )
        return data

    def get_report(self, identifier):
        with self._lock:
            row = self._connection.execute(
                "SELECT data_json FROM release_reports WHERE id=?", (identifier,)
            ).fetchone()
            if not row:
                raise KeyError("release report不存在")
            return load_json(row[0], {})

    def notification(self, channel):
        with self._lock:
            row = self._connection.execute(
                "SELECT data_json FROM notification_state WHERE channel=?", (channel,)
            ).fetchone()
            return load_json(row[0], {}) if row else None

    def save_notification(self, channel, data):
        with self.transaction():
            self._connection.upsert(
                "notification_state",
                {
                    "channel": channel,
                    "data_json": dump_json(data),
                },
                update=["data_json"],
            )

    def notification_deliveries(self):
        with self._lock:
            return [
                {"state_key": row["channel"], **load_json(row["data_json"], {})}
                for row in self._connection.execute(
                    "SELECT channel,data_json FROM notification_state"
                ).fetchall()
            ]

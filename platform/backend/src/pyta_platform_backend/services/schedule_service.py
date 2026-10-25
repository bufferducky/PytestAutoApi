"""到点计算使用APScheduler；平台DB拥有计划/outbox，不在扫描器里跑业务。"""

from datetime import datetime, timedelta, timezone
from threading import Event, RLock, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from fastapi import HTTPException

from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.schemas.assets import AssetRunRequest
from pyta_platform_backend.schemas.run import CreateRunRequest
from pyta_platform_backend.schemas.schedules import ScheduleDefinition
from pyta_platform_backend.services.redaction import Redactor


def utcnow():
    return datetime.now(timezone.utc)


def next_fire(data, after):
    # 标准crontab星期0/7=周日；APScheduler数字0=周一，必须显式转星期名。
    fields = data["cron"].split()
    if len(fields) != 5:
        raise ValueError("cron必须为5段标准crontab")
    weekday = fields[4]
    names = ["sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    if weekday != "*" and any(char.isdigit() for char in weekday):
        days = []
        for part in weekday.split(","):
            interval = part.split("/")
            if len(interval) > 2:
                raise ValueError("非法星期表达式")
            base = interval[0]
            step = int(interval[1]) if len(interval) == 2 else 1
            if step < 1 or step > 7:
                raise ValueError("非法星期步长")
            if base == "*":
                start, end = 0, 6
            elif "-" in base:
                start, end = map(int, base.split("-"))
            else:
                start = end = int(base)
            if not 0 <= start <= end <= 7:
                raise ValueError("星期范围须0—7")
            days.extend(names[day] for day in range(start, end + 1, step))
        fields[4] = ",".join(dict.fromkeys(days))
    trigger = CronTrigger.from_crontab(" ".join(fields), timezone=ZoneInfo(data["timezone"]))
    result = trigger.get_next_fire_time(None, after + timedelta(microseconds=1))
    if result is None:
        raise ValueError("cron没有下一触发时间")
    return result.astimezone(timezone.utc)


class ScheduleService:
    def __init__(self, repository, assets, run_service, worker_host, management, *, clock=utcnow):
        self.repository, self.assets, self.runs, self.worker_host = (
            repository,
            assets,
            run_service,
            worker_host,
        )
        self.clock = clock
        self.last_tick = None
        self.last_error = None
        self._lock = RLock()

    def get(self, identifier):
        try:
            return self.repository.schedule(identifier)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def save(self, data, identifier=None, revision=None):
        try:
            model = ScheduleDefinition(**data)
            values = model.model_dump() if hasattr(model, "model_dump") else model.dict()
            next_at = next_fire(values, self.clock())
            if Redactor(values).clean(values) != values:
                raise ValueError("计划只能保存公开值与秘密引用")
            self.assets.version("suites", values["suite_id"], values["suite_version"])
            # 创建时就验证固定计划，不发送业务请求。
            self.assets.plan(
                "suites",
                values["suite_id"],
                values["suite_version"],
                AssetRunRequest(
                    transport_mode=values["transport_mode"],
                    environment_id=values["environment_id"],
                    parameters=values["parameters"],
                ),
            )
            return self.repository.save_schedule(
                {
                    "id": identifier or uuid4().hex,
                    **values,
                    "next_fire_at": next_at.isoformat(),
                    "migration_required": None,
                },
                revision,
            )
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, Redactor(data).clean(str(exc))) from exc

    def change_status(self, identifier, revision, status):
        current = self.get(identifier)
        if current["revision"] != revision:
            raise HTTPException(409, "计划已修改")
        if status == "active" and current.get("migration_required"):
            raise HTTPException(409, current["migration_required"])
        if status == "deleted":
            try:
                return self.repository.save_schedule(
                    {**current, "status": "deleted", "next_fire_at": None}, revision
                )
            except RunConflict as exc:
                raise HTTPException(409, str(exc)) from exc
        public = {
            k: v
            for k, v in current.items()
            if k not in {"id", "revision", "next_fire_at", "migration_required"}
        }
        return self.save({**public, "status": status}, identifier, revision)

    def preview(self, identifier, count=5):
        current = self.get(identifier)
        at = self.clock()
        items = []
        for _ in range(min(10, max(1, count))):
            at = next_fire(current, at)
            items.append(at.astimezone(ZoneInfo(current["timezone"])).isoformat())
        return {"timezone": current["timezone"], "times": items, "network_executed": False}

    def _plan(self, schedule):
        plan = self.assets.plan(
            "suites",
            schedule["suite_id"],
            schedule["suite_version"],
            AssetRunRequest(
                transport_mode=schedule["transport_mode"],
                environment_id=schedule["environment_id"],
                parameters=schedule["parameters"],
            ),
        )
        plan.update(
            queue_timeout_seconds=schedule["queue_timeout_seconds"],
            timeout_seconds=schedule["timeout_seconds"],
            concurrency_keys=schedule["concurrency_keys"],
        )
        if Redactor(plan).clean(plan) != plan:
            raise ValueError("调度快照不能包含秘密值")
        return plan

    def _deliver(self, trigger):
        if trigger["state"] != "pending":
            return trigger
        schedule = self.get(trigger["schedule_id"])
        if schedule["status"] != "active" or schedule["revision"] != trigger["schedule_revision"]:
            return self.repository.set_trigger(
                {
                    **trigger,
                    "state": "cancelled_before_dispatch",
                    "message": "计划已暂停/修改，未投递",
                }
            )
        response = self.runs._create_prepared(
            CreateRunRequest(
                suite_id=schedule["suite_id"],
                environment_id=schedule["environment_id"],
                trigger_source="scheduler",
                requested_by="scheduler",
                payload=trigger["payload"],
            ),
            None,
            idempotency_key="schedule:" + trigger["id"],
        )
        trigger = {
            **trigger,
            "run_id": response.run_id,
            "state": "queued",
            "fired_at": self.clock().isoformat(),
        }
        self.repository.set_trigger(trigger)
        self.worker_host.wake()
        return trigger

    def tick(self, now=None, recovering=False):
        with self._lock:
            now = now or self.clock()
            self.last_error = None
            events = []
            try:
                for pending in self.repository.triggers():
                    if pending["state"] == "pending":
                        events.append(self._deliver(pending))
                for schedule in self.repository.schedules():
                    if schedule["status"] != "active" or not schedule["next_fire_at"]:
                        continue
                    cursor = datetime.fromisoformat(schedule["next_fire_at"])
                    due = []
                    while cursor <= now and len(due) < 1000:
                        due.append(cursor)
                        cursor = next_fire(schedule, cursor)
                    if not due:
                        continue
                    if len(due) == 1000 and cursor <= now:
                        self.last_error = "错过超过1000次，请人工核对；未补跑业务"
                        continue
                    missed = recovering or len(due) > 1 or (now - due[0]).total_seconds() > 60
                    fire = due[-1] if missed and schedule["missed_policy"] == "fire_once" else None
                    if not missed:
                        fire = due[0]
                    for planned in due:
                        state = "missed" if planned != fire else "pending"
                        plan = {}
                        message = "停机/错过，未执行" if state == "missed" else None
                        if state == "pending":
                            busy = bool(self.runs.repository.list_running_records())
                            if busy and schedule["busy_policy"] == "skip":
                                state, message = "busy_skipped", "执行槽忙，按策略跳过"
                            else:
                                try:
                                    plan = self._plan(schedule)
                                except Exception as exc:
                                    state, message = "blocked", Redactor().clean(str(exc))
                        trigger = self.repository.trigger(
                            schedule, planned.isoformat(), state, plan, message
                        )
                        if trigger:
                            events.append(self._deliver(trigger))
                    self.repository.advance(
                        schedule["id"], schedule["revision"], cursor.isoformat()
                    )
                self.last_tick = now.isoformat()
            except Exception as exc:
                self.last_error = type(exc).__name__
                raise
            return events

    def pause_all(self):
        changed = []
        for schedule in self.repository.schedules():
            if schedule["status"] == "active":
                changed.append(self.change_status(schedule["id"], schedule["revision"], "paused"))
        return changed

    def latest_backup(self):
        from pathlib import Path

        if "://" in str(self.repository._database_path):
            return None
        path = Path(self.repository._database_path)
        if str(path) == ":memory:":
            return None
        backups = list(path.parent.glob(path.name + "*backup-*.sqlite3"))
        return max(backups, key=lambda file: file.stat().st_mtime).name if backups else None

    def status(self):
        queued = self.runs.repository.list_queued_records()
        return {
            "last_tick": self.last_tick,
            "database_integrity": (
                "ok"
                if self.runs.repository._connection.execute("SELECT 1").fetchone()[0] == 1
                else "unavailable"
            )
            if hasattr(self.runs.repository, "_connection")
            else "memory",
            "storage_path": "configured_database",
            "lease_states": {
                "needs_reconciliation": sum(
                    row["state"] == "needs_reconciliation"
                    for row in self.resources.repository.pool()
                )
            }
            if hasattr(self, "resources")
            else {},
            "latest_backup": self.latest_backup(),
            "last_error": self.last_error,
            "worker_available": self.worker_host.available,
            "worker_heartbeat": getattr(self.worker_host, "last_heartbeat", None),
            "worker_error": self.worker_host.last_error,
            "notification_error": getattr(self.worker_host, "notification_error", None),
            "queued": len(queued),
            "oldest_queued_at": queued[0].created_at.isoformat() if queued else None,
            "active_schedules": sum(s["status"] == "active" for s in self.repository.schedules()),
            "unverified_company_risks": ["S" + str(i).zfill(2) for i in range(1, 17)],
        }


class ScheduleHost:
    def __init__(self, service, interval_seconds=30):
        self.service, self.interval = service, max(0.1, interval_seconds)
        self._stop = Event()
        self._thread = None

    def start(self):
        self.service.tick(recovering=True)
        self._thread = Thread(target=self._loop, name="testflow-scheduler", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.service.tick()
            except Exception:
                pass  # 已保留service.last_error，不改变业务run结果。

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

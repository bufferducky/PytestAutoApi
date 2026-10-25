"""运行事实仓储。所有认领/回写均在事务内校验，队列不拥有运行状态。"""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from pyta_platform_backend.db.store import Store
from pyta_platform_backend.repositories.sqlite_support import (
    dump_datetime,
    dump_json,
    load_datetime,
    load_json,
)
from pyta_platform_backend.schemas.run import (
    CreateRunRequest,
    ListRunsResponse,
    RunDetailResponse,
    RunStatus,
    RunSummaryResponse,
    UpdateRunStatusRequest,
)
from pyta_platform_backend.services.redaction import Redactor


class RunConflict(ValueError):
    """状态/版本/attempt 冲突；调用层映射为 409。"""


@dataclass
class RunRecord:
    run_id: str
    suite_id: str
    environment_id: Optional[str]
    environment_name: Optional[str]
    trigger_source: str
    requested_by: str
    payload: dict
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status_message: Optional[str] = None
    execution: dict = field(default_factory=dict)


def utcnow():
    return datetime.now(timezone.utc)


class InMemoryRunRepository:
    def __init__(self):
        self._records = {}
        self._lock = RLock()

    @contextmanager
    def _transaction(self):
        with self._lock:
            yield

    def _save(self, record):
        self._records[record.run_id] = deepcopy(record)

    def get_by_id(self, run_id):
        with self._lock:
            return deepcopy(self._records.get(run_id))

    def _all(self):
        return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    def create_pending_run(
        self, payload: CreateRunRequest, *, environment_name=None, idempotency_key=None
    ):
        public = Redactor(payload.payload).clean(payload.payload)
        now = utcnow()
        record = RunRecord(
            run_id=hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]
            if idempotency_key
            else uuid4().hex,
            suite_id=payload.suite_id,
            environment_id=payload.environment_id,
            environment_name=environment_name,
            trigger_source=payload.trigger_source,
            requested_by=payload.requested_by,
            payload=public,
            status=RunStatus.QUEUED,
            created_at=now,
            updated_at=now,
            execution={
                "version": 0,
                "results": [],
                "attempts": [],
                "counts": {},
                "cleanup_status": "not_started",
                "definition_hash": hashlib.sha256(
                    json.dumps(public, sort_keys=True).encode()
                ).hexdigest(),
                "original_run_id": payload.payload.get("original_run_id"),
            },
        )
        with self._transaction():
            existing = self.get_by_id(record.run_id)
            if existing is not None:
                if existing.payload != record.payload:
                    raise RunConflict("幂等键已绑定不同快照")
                return existing
            self._save(record)
        return record

    def get_detail(self, run_id):
        record = self.get_by_id(run_id)
        return self._to_detail(record) if record else None

    def list_runs(self, limit, offset):
        with self._lock:
            records = self._all()
            return ListRunsResponse(
                total=len(records),
                limit=limit,
                offset=offset,
                items=[self._to_summary(r) for r in records[offset : offset + limit]],
            )

    def list_queued_records(self):
        with self._lock:
            return [r for r in reversed(self._all()) if r.status == RunStatus.QUEUED]

    def list_running_records(self):
        with self._lock:
            return [r for r in self._all() if r.status == RunStatus.RUNNING]

    def _require(self, run_id):
        record = self.get_by_id(run_id)
        if record is None:
            raise KeyError(run_id)
        return record

    @staticmethod
    def _check(record, expected_version=None, attempt_id=None):
        if expected_version is not None and record.execution.get("version", 0) != expected_version:
            raise RunConflict("run 版本已变化")
        if attempt_id is not None and record.execution.get("attempt_id") != attempt_id:
            raise RunConflict("attempt 已失效，拒绝迟到回写")

    def _store_change(self, record):
        record.updated_at = utcnow()
        record.execution["version"] = record.execution.get("version", 0) + 1
        self._save(record)
        return self._to_detail(record)

    def claim(self, run_id, timeout_seconds=300):
        with self._transaction():
            record = self._require(run_id)
            if record.status != RunStatus.QUEUED:
                raise RunConflict("run 不在待执行状态")
            record.status = RunStatus.RUNNING
            record.started_at = utcnow()
            attempt_id = uuid4().hex
            deadline = record.started_at + timedelta(seconds=timeout_seconds)
            record.execution.update(
                attempt_id=attempt_id,
                deadline_at=deadline.isoformat(),
                cleanup_status="not_started",
            )
            record.execution.setdefault("attempts", []).append(
                {
                    "attempt_id": attempt_id,
                    "started_at": record.started_at.isoformat(),
                    "deadline_at": deadline.isoformat(),
                }
            )
            record.status_message = "worker claimed"
            return self._store_change(record)

    def update_status(self, run_id, payload: UpdateRunStatusRequest):
        # 外部 PATCH 不能伪造执行结果；终态只能由持有 attempt 的 worker 提交。
        if payload.status == RunStatus.RUNNING:
            with self._transaction():
                record = self._require(run_id)
                self._check(record, payload.expected_version, payload.attempt_id)
                if payload.expected_version is None:
                    raise RunConflict("状态更新必须提供 expected_version")
                return self.claim(run_id)
        raise RunConflict("终态由 worker 按执行证据提交；取消请使用 cancel 接口")

    def append_result(self, run_id, attempt_id, result, counts):
        with self._transaction():
            record = self._require(run_id)
            self._check(record, attempt_id=attempt_id)
            if record.status != RunStatus.RUNNING:
                raise RunConflict("终态不能追加结果")
            results = record.execution.setdefault("results", [])
            if any(r["case_id"] == result["case_id"] for r in results):
                raise RunConflict("重复 case 结果")
            results.append(result)
            record.execution["counts"] = counts
            return self._store_change(record)

    def finish(
        self, run_id, attempt_id, status, message, *, counts=None, cleanup_status="not_started"
    ):
        with self._transaction():
            record = self._require(run_id)
            self._check(record, attempt_id=attempt_id)
            if record.status != RunStatus.RUNNING or status in {
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            }:
                raise RunConflict("非法终态转换")
            if record.execution.get("cancel_requested_at") and status not in {
                RunStatus.INTERRUPTED,
                RunStatus.TIMED_OUT,
            }:
                status = RunStatus.CANCELLED
            record.status, record.finished_at = status, utcnow()
            record.status_message = message
            record.execution["cleanup_status"] = cleanup_status
            if counts is not None:
                record.execution["counts"] = counts
            attempt = record.execution["attempts"][-1]
            attempt.update(status=status.value, finished_at=record.finished_at.isoformat())
            return self._store_change(record)

    def prune_evidence(self, run_id):
        with self._transaction():
            record = self._require(run_id)
            if record.execution.get("migration"):
                raise RunConflict("迁入历史证据受保护，不能回收")
            if record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                raise RunConflict("不能清理活跃run")
            first_error = next(
                (
                    case.get("error")
                    or next(
                        (
                            a.get("message")
                            for s in case.get("steps", [])
                            for a in s.get("assertions", [])
                            if a["status"] != "passed"
                        ),
                        None,
                    )
                    for case in record.execution.get("results", [])
                    if case["status"] not in {"passed", "skipped"}
                ),
                None,
            )
            record.execution["retention_summary"] = first_error or record.status_message
            record.execution["results"] = []
            record.execution["evidence_pruned_at"] = utcnow().isoformat()
            record.payload = {
                key: value
                for key, value in record.payload.items()
                if key
                in {
                    "execution_mode",
                    "transport_mode",
                    "asset_ref",
                    "scenario_refs",
                    "scenario_version_ref",
                    "context_snapshots",
                    "environment",
                    "original_run_id",
                }
            }
            record.status_message = "详细证据保留期已过；状态、版本、计数和摘要仍保留"
            return self._store_change(record)

    def update_cleanup(self, run_id, status):
        if status not in {"succeeded", "cleanup_failed", "needs_reconciliation"}:
            raise ValueError("非法清理状态")
        with self._transaction():
            record = self._require(run_id)
            if record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                raise RunConflict("活动run由worker写清理状态")
            record.execution["cleanup_status"] = status
            return self._store_change(record)

    def cancel(self, run_id):
        with self._transaction():
            record = self._require(run_id)
            if record.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                raise RunConflict("run 已结束，不能取消")
            record.execution.setdefault("cancel_requested_at", utcnow().isoformat())
            if record.status == RunStatus.QUEUED:
                record.status, record.finished_at = RunStatus.CANCELLED, utcnow()
            record.status_message = "已请求取消；已到达服务端的请求不保证撤回"
            return self._store_change(record)

    def recover_interrupted(self):
        with self._transaction():
            for record in self._all():
                if record.status == RunStatus.RUNNING and not record.execution.get(
                    "migration", {}
                ).get("do_not_resume"):
                    record.status, record.finished_at = RunStatus.INTERRUPTED, utcnow()
                    record.status_message = "worker 中断；未自动重放，需检查已发请求与待清理资源"
                    record.execution["cleanup_status"] = "needs_reconciliation"
                    if record.execution.get("attempts"):
                        record.execution["attempts"][-1].update(
                            status="interrupted",
                            finished_at=record.finished_at.isoformat(),
                        )
                    self._store_change(record)

    @staticmethod
    def _to_summary(record):
        e, p = record.execution, record.payload
        mode = p.get("transport_mode", "historical_unknown")
        counts = e.get("counts", {})
        eligible = (
            record.status == RunStatus.SUCCEEDED
            and not e.get("migration")
            and not e.get("evidence_pruned_at")
            and p.get("execution_mode") == "standard_run"
            and not p.get("rerun_selection", {}).get("partial")
            and mode == "live"
            and counts.get("assertions", 0) > 0
            and counts.get("skipped", 0) == 0
            and counts.get("blocked", 0) == 0
            and e.get("cleanup_status") == "succeeded"
        )
        return RunSummaryResponse(
            run_id=record.run_id,
            suite_id=record.suite_id,
            environment_id=record.environment_id,
            environment_name=record.environment_name,
            trigger_source=record.trigger_source,
            requested_by=record.requested_by,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            execution_mode=p.get("execution_mode", "historical_unknown"),
            transport_mode=mode,
            validation_scope="historical_demo"
            if e.get("migration")
            else "simulated_partial"
            if mode == "mock" and p.get("rerun_selection", {}).get("partial")
            else "live_partial"
            if mode == "live" and p.get("rerun_selection", {}).get("partial")
            else "simulated"
            if mode == "mock"
            else "live"
            if mode == "live"
            else "historical_unknown",
            legacy_sensitive=Redactor(record.payload).clean(record.payload) != record.payload,
            definition_hash=e.get("definition_hash"),
            scenario_version_ref=p.get("scenario_version_ref"),
            version=e.get("version", 0),
            attempt_id=e.get("attempt_id"),
            counts=counts,
            cleanup_status=e.get("cleanup_status", "not_recorded"),
            eligible_for_release=eligible,
        )

    @classmethod
    def _to_detail(cls, record):
        e = record.execution
        redactor = Redactor(record.payload)
        redactor.remember(e.get("results", []))
        return RunDetailResponse(
            **cls._dump_model(cls._to_summary(record)),
            payload=redactor.clean(record.payload),
            status_message=redactor.clean(record.status_message),
            results=redactor.clean(e.get("results", [])),
            cancel_requested_at=e.get("cancel_requested_at"),
            deadline_at=e.get("deadline_at"),
            original_run_id=e.get("original_run_id"),
            evidence_pruned_at=e.get("evidence_pruned_at"),
            retention_summary=e.get("retention_summary"),
        )

    @staticmethod
    def _dump_model(model):
        return model.model_dump() if hasattr(model, "model_dump") else model.dict()


class SqlRunRepository(InMemoryRunRepository):
    """SQLAlchemy 运行仓储；事实与 outbox 在同一写事务提交。"""

    def __init__(self, database_path):
        super().__init__()
        self._database_path = database_path
        self._connection = Store(database_path)

    @contextmanager
    def _transaction(self):
        with self._lock, self._connection.transaction():
            yield

    def _save(self, r):
        values = {
            "run_id": r.run_id,
            "suite_id": r.suite_id,
            "environment_id": r.environment_id,
            "environment_name": r.environment_name,
            "trigger_source": r.trigger_source,
            "requested_by": r.requested_by,
            "payload_json": dump_json(r.payload),
            "status": r.status.value,
            "created_at": dump_datetime(r.created_at),
            "updated_at": dump_datetime(r.updated_at),
            "started_at": dump_datetime(r.started_at),
            "finished_at": dump_datetime(r.finished_at),
            "status_message": r.status_message,
            "execution_json": dump_json(r.execution),
        }
        self._connection.upsert(
            "runs",
            values,
            update=[
                "status",
                "updated_at",
                "payload_json",
                "started_at",
                "finished_at",
                "status_message",
                "execution_json",
            ],
        )
        if r.status == RunStatus.QUEUED and not r.execution.get("migration", {}).get(
            "do_not_resume"
        ):
            self._connection.upsert(
                "run_outbox",
                {
                    "run_id": r.run_id,
                    "state": "pending",
                    "owner": None,
                    "attempt": 0,
                    "lease_until": None,
                    "priority": 0,
                    "created_at": dump_datetime(r.created_at),
                },
                ignore=True,
            )
        elif r.status != RunStatus.QUEUED:
            self._connection.execute(
                "UPDATE run_outbox SET state=? WHERE run_id=?",
                ("claimed" if r.status == RunStatus.RUNNING else "done", r.run_id),
            )

    def list_queued_records(self):
        return [
            r
            for r in super().list_queued_records()
            if not r.execution.get("migration", {}).get("do_not_resume")
        ]

    def list_running_records(self):
        return [
            r
            for r in super().list_running_records()
            if not r.execution.get("migration", {}).get("do_not_resume")
        ]

    def live_stats(self):
        # JSON predicates are compiled per dialect; imported demo history never counts as live.
        from sqlalchemy import and_, case, func, select

        from pyta_platform_backend.db.schema import runs

        # JSON null semantics differ across MySQL/SQLite; missing source marker is reliable.
        live = and_(
            runs.c.payload_json["transport_mode"].as_string() == "live",
            runs.c.execution_json["migration"]["source"].as_string().is_(None),
        )
        statement = select(
            func.count().label("total"),
            func.sum(case((runs.c.status == "queued", 1), else_=0)).label("queued"),
            func.sum(case((runs.c.status == "running", 1), else_=0)).label("running"),
            func.sum(
                case(
                    (
                        runs.c.status.in_(
                            [
                                "failed",
                                "error",
                                "timed_out",
                                "interrupted",
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("failed"),
        ).where(live)
        row = self._connection.execute(statement).fetchone()
        return {k: int(v or 0) for k, v in row.items()}

    def get_by_id(self, run_id):
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def _all(self):
        return [
            self._row_to_record(row)
            for row in self._connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC"
            ).fetchall()
        ]

    @staticmethod
    def _row_to_record(row):
        return RunRecord(
            run_id=row["run_id"],
            suite_id=row["suite_id"],
            environment_id=row["environment_id"],
            environment_name=row["environment_name"],
            trigger_source=row["trigger_source"],
            requested_by=row["requested_by"],
            payload=load_json(row["payload_json"], {}),
            status=RunStatus(row["status"]),
            created_at=load_datetime(row["created_at"]),
            updated_at=load_datetime(row["updated_at"]),
            started_at=load_datetime(row["started_at"]),
            finished_at=load_datetime(row["finished_at"]),
            status_message=row["status_message"],
            execution=load_json(row["execution_json"], {}),
        )


# 旧测试/外部导入名兼容；生产装配使用 SqlRunRepository。
SqliteRunRepository = SqlRunRepository

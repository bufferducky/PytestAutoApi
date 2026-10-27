"""worker 只执行已持久登记并原子认领的任务；不提供固定成功兜底。"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from pyta_platform_backend.repositories.run_repository import RunConflict
from pyta_platform_backend.schemas.run import RunStatus
from pyta_platform_backend.services.redaction import Redactor
from pyta_platform_backend.services.run_validation import load_definition, validate_live_payload
from pyta_platform_backend.workers.context_transport import (
    ContextAuthPlugin,
    ContextTransport,
    resolve_references,
)
from pyta_platform_backend.workers.dispatcher import DispatchTask
from testflow_engine import (
    BootstrapAuthPlugin,
    HttpxTransport,
    LegacyCachePlugin,
    TestFlowEngine,
)


@dataclass(frozen=True)
class WorkerExecutionResult:
    status: RunStatus
    status_message: Optional[str] = None


class RunWorker:
    def __init__(self, dispatcher, run_service, handler: Optional[Callable] = None):
        self._dispatcher, self._run_service, self._handler = dispatcher, run_service, handler
        self.resource_repository = None

    def run_next(self):
        task = self._dispatcher.pull_next()
        if task is None:
            queued = self._run_service.repository.list_queued_records()
            if queued:
                record = queued[0]
                # 提示丢失不丢任务；公开快照若含脱敏凭证会明确阻塞/报错，不重放占位。
                task = DispatchTask(
                    run_id=record.run_id,
                    suite_id=record.suite_id,
                    trigger_source=record.trigger_source,
                    requested_by=record.requested_by,
                    payload=record.payload,
                    dispatched_at=record.created_at,
                )
        return self._consume_task(task)

    def run_by_id(self, run_id):
        return self._consume_task(self._dispatcher.pull_by_run_id(run_id))

    def _consume_task(self, task):
        if task is None:
            return None
        repo = self._run_service.repository
        stored = repo.get_by_id(task.run_id)
        if stored:
            if stored.execution.get("migration", {}).get("do_not_resume"):
                return None
            if stored.payload.get("execution_mode") == "evaluation":
                return None
            try:
                validate_live_payload(stored.payload)
            except (ValueError, TypeError):
                return None
        before = repo.get_detail(task.run_id)
        if before is None or before.status != RunStatus.QUEUED:
            return None
        if task.payload.get("execution_mode") == "evaluation":
            return None
        try:
            validate_live_payload(task.payload)
        except (ValueError, TypeError, OSError):
            # Historical/invalid queued rows are not executable and must keep their evidence.
            return None
        queue_budget = task.payload.get("queue_timeout_seconds")
        if (
            queue_budget is not None
            and (datetime.now(timezone.utc) - before.created_at).total_seconds() > queue_budget
        ):
            claimed = repo.claim(task.run_id)
            return repo.finish(
                task.run_id,
                claimed.attempt_id,
                RunStatus.TIMED_OUT,
                "排队预算已耗尽；未发送业务请求",
                cleanup_status="succeeded",
            )
        try:
            claimed = repo.claim(task.run_id, task.payload.get("timeout_seconds", 300))
        except RunConflict:
            return None
        attempt_id = claimed.attempt_id
        redactor = Redactor(task.payload)
        counts = {
            "planned": 0,
            "total": 0,
            "executed": 0,
            "requests": 0,
            "assertions": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "blocked": 0,
        }
        cleanup_status, engine, persistence_error = "not_started", None, None

        def stop():
            if persistence_error:
                return "error"
            detail = repo.get_detail(task.run_id)
            return "cancelled" if detail.cancel_requested_at else None

        def record(result, phase):
            nonlocal persistence_error
            raw = result.model_dump() if hasattr(result, "model_dump") else result.dict()
            redactor.remember(raw)
            clean = redactor.clean(raw)
            clean["phase"] = phase
            for step in clean["steps"]:
                for key in ["request", "response", "error"]:
                    if key in step:
                        step[key] = redactor.bounded(step[key])
                for assertion in step["assertions"]:
                    assertion["actual"] = redactor.bounded(assertion["actual"])
                    assertion["expected"] = redactor.bounded(assertion["expected"])
            if phase == "main":
                counts["total"] += 1
                counts["executed"] += int(any(s.request_sent for s in result.steps))
                counts["requests"] += sum(
                    max(
                        int(s.request_sent),
                        s.network_attempt_count + s.http_replay_count,
                        s.http_attempt_count,
                    )
                    for s in result.steps
                )
                counts["assertions"] += sum(len(s.assertions) for s in result.steps)
                key = {
                    "passed": "passed",
                    "failed": "failed",
                    "error": "errors",
                    "skipped": "skipped",
                    "blocked": "blocked",
                }.get(result.status.value)
                if key:
                    counts[key] += 1
            else:
                counts["cleanup_requests"] = counts.get("cleanup_requests", 0) + sum(
                    s.request_sent for s in result.steps
                )
            if not persistence_error:
                try:
                    repo.append_result(task.run_id, attempt_id, clean, deepcopy(counts))
                except Exception as exc:
                    # 证据写入失败后停止业务，但让引擎 finally 仍能清理已创建对象。
                    persistence_error = exc

        try:
            definition = load_definition(task.payload)
        except (ValueError, TypeError, OSError) as exc:
            return repo.finish(
                task.run_id,
                attempt_id,
                RunStatus.ERROR,
                redactor.clean(str(exc)),
                counts=counts,
                cleanup_status="not_started",
            )
        if task.payload.get("execution_mode") == "ui_journey":
            from pyta_platform_backend.runners.journey_worker import run_ui

            return run_ui(self, task, claimed, redactor)
        try:
            definition.run_id = task.run_id
            counts["planned"] = len(definition.cases)
            raw = (
                definition.model_dump() if hasattr(definition, "model_dump") else definition.dict()
            )
            redactor.remember(raw)
            definition.variables = self._merge_environment_variables(task, definition.variables)
            if task.payload.get("context_snapshots"):
                definition.variables["host"] = task.payload["context_snapshots"]["default"][
                    "target"
                ]["base_url"]
            if task.payload.get("transport_mode") == "live":
                definition.variables = resolve_references(definition.variables, redactor._collect)
            if self._handler is not None:
                receipt = self._handler(task)
                status, message = receipt.status, receipt.status_message
                if status == RunStatus.SUCCEEDED:
                    status, message = RunStatus.BLOCKED, "handler 未提供可验证的步骤证据"
            else:
                engine = self._build_engine_for_task(
                    task,
                    definition.variables,
                    max(0.001, (claimed.deadline_at - datetime.now(timezone.utc)).total_seconds()),
                    redactor,
                )
                if definition.metadata.get("business_database_plan"):
                    import time

                    from pyta_platform_backend.workers.business_database_plugin import (
                        BusinessDatabasePlugin,
                    )

                    plugin = BusinessDatabasePlugin(
                        definition.metadata["business_database_plan"],
                        task.payload.get("context_snapshots", {}),
                        deadline=time.monotonic()
                        + max(
                            0, (claimed.deadline_at - datetime.now(timezone.utc)).total_seconds()
                        ),
                        should_stop=stop,
                        redactor=redactor,
                    )
                    plugin.prepare(definition)
                    counts["planned"] = len(definition.cases)
                    engine.plugins.append(plugin)
                elif any(
                    case.enabled and case.metadata.get("database_check")
                    for case in definition.cases
                ):
                    raise ValueError("business_database_plan_missing")
                if definition.metadata.get("fixture_plan"):
                    from pyta_platform_backend.workers.resource_plugin import ResourcePlugin

                    if self.resource_repository is None:
                        raise ValueError("资源仓储不可用")
                    engine.plugins.append(
                        ResourcePlugin(
                            self.resource_repository,
                            engine.transport,
                            task.payload.get("context_snapshots", {}),
                            definition.metadata["fixture_plan"],
                            redactor=redactor,
                        )
                    )
                result = engine.execute_run(
                    definition,
                    on_case_result=record,
                    should_stop=stop,
                    timeout_seconds=max(
                        0, (claimed.deadline_at - datetime.now(timezone.utc)).total_seconds()
                    ),
                    cleanup_timeout_seconds=task.payload.get("cleanup_timeout_seconds", 60),
                )
                cleanup_status = result.cleanup_status
                counts["authentication_requests"] = len(result.authentication_results)
                if persistence_error:
                    raise RuntimeError(f"结构结果存储失败: {persistence_error}")
                status = RunStatus(
                    "succeeded" if result.status.value == "passed" else result.status.value
                )
                prefix = (
                    f"legacy yaml executed from {task.payload.get('legacy_yaml_path')}"
                    if task.payload["execution_mode"] == "legacy_yaml"
                    else "standard run executed"
                )
                message = result.error or f"{prefix}: " + " ".join(
                    f"{k}={v}" for k, v in counts.items()
                )
            return repo.finish(
                task.run_id,
                attempt_id,
                status,
                redactor.clean(message),
                counts=counts,
                cleanup_status=cleanup_status,
            )
        except Exception as exc:
            failure_status = getattr(exc, "execution_status", None)
            return repo.finish(
                task.run_id,
                attempt_id,
                RunStatus(failure_status)
                if failure_status in {"cancelled", "timed_out"}
                else RunStatus.ERROR,
                redactor.clean(str(exc)),
                counts=counts,
                cleanup_status=cleanup_status,
            )
        finally:
            if engine is not None and hasattr(engine.transport, "close"):
                engine.transport.close()

    @staticmethod
    def _build_engine_for_task(task, variables=None, timeout_seconds=30, redactor=None):
        validate_live_payload(task.payload)
        plugins = [LegacyCachePlugin()]
        if task.payload.get("context_snapshots"):
            transport = ContextTransport(
                task.payload["context_snapshots"],
                remember_secret=redactor._collect if redactor else None,
                timeout_seconds=timeout_seconds,
            )
            return TestFlowEngine(
                transport=transport, plugins=plugins + [ContextAuthPlugin(transport)]
            )
        if (variables or {}).get("auth_bootstrap"):
            plugins.append(BootstrapAuthPlugin(timeout_seconds=timeout_seconds))
        transport = HttpxTransport()
        return TestFlowEngine(transport=transport, plugins=plugins)

    @staticmethod
    def _merge_environment_variables(task: DispatchTask, variables):
        merged = deepcopy(variables)
        environment = deepcopy(task.payload.get("environment", {}))
        if environment:
            merged.setdefault("environment", environment)
            if not merged.get("host") and environment.get("base_url"):
                merged["host"] = environment["base_url"]
        return merged

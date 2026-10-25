"""把UI旅程回写统一run；缺驱动/设备能力blocked，不用假驱动兜底。"""

from datetime import datetime, timezone
from time import monotonic

from pyta_platform_backend.runners.journey_resources import JourneyResources
from pyta_platform_backend.runners.ui import (
    AndroidSession,
    WebSession,
    capability,
    device_preflight,
    execute_journey,
)
from pyta_platform_backend.schemas.run import RunStatus
from pyta_platform_backend.workers.context_transport import ContextError, secret_value
from testflow_engine import CaseExecutionResult, ExecutionStatus


def run_ui(worker, task, claimed, redactor):
    repo = worker._run_service.repository
    data = task.payload["journey_definition"]["data"]
    profile = task.payload.get("device_profile", {}).get("data")
    session = None
    lease = None
    api_resources = None
    counts = {
        "planned": len(data["actions"]),
        "total": 0,
        "executed": 0,
        "requests": 0,
        "assertions": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "blocked": 0,
        "skipped": 0,
    }

    def record_case(case):
        counts["total"] += 1
        counts["executed"] += int(case.status.value != "blocked")
        counts["assertions"] += sum(len(s.assertions) for s in case.steps)
        counts["requests"] += sum(int(s.request_sent) for s in case.steps)
        key = {
            "passed": "passed",
            "failed": "failed",
            "error": "errors",
            "blocked": "blocked",
        }.get(case.status.value)
        if key:
            counts[key] += 1
        raw = case.model_dump() if hasattr(case, "model_dump") else case.dict()
        repo.append_result(task.run_id, claimed.attempt_id, redactor.clean(raw), dict(counts))

    def block_unexecuted(message):
        recorded = {case["case_id"] for case in repo.get_detail(task.run_id).results}
        for action in data["actions"]:
            if action["step_id"] in recorded:
                continue
            now = datetime.now(timezone.utc)
            record_case(
                CaseExecutionResult(
                    case_id=action["step_id"],
                    title=action["name"],
                    status=ExecutionStatus.BLOCKED,
                    error=message,
                    steps=[],
                    started_at=now,
                    finished_at=now,
                    metadata={
                        "runner_type": data["runner_type"],
                        "runner_version": "ui-runner@1",
                        "phase": "verify",
                    },
                )
            )

    try:
        status = capability(data, profile)
        if not status["available"]:
            block_unexecuted(",".join(status["blocked_reasons"]))
            return repo.finish(
                task.run_id,
                claimed.attempt_id,
                RunStatus.BLOCKED,
                ",".join(status["blocked_reasons"]),
                counts=counts,
                cleanup_status="succeeded",
            )
        snapshot = task.payload["context_snapshots"]["default"]
        binding = snapshot.get("binding") or {}
        identity = snapshot.get("identity") or {}
        context = {
            "identity": {
                "alias": identity.get("name"),
                "username": {"secret_ref": identity.get("username_secret_ref")}
                if identity
                else None,
                "password": {"secret_ref": identity.get("password_secret_ref")}
                if identity
                else None,
            },
            "params": {},
            "fixtures": {},
            "runtime": {},
        }
        data = {**data, "_base_url": snapshot["target"]["base_url"]}
        if data["runner_type"] == "android":
            probe = device_preflight(profile)
            if not probe["available"]:
                block_unexecuted(str(probe["blocked_reasons"]))
                return repo.finish(
                    task.run_id,
                    claimed.attempt_id,
                    RunStatus.BLOCKED,
                    str(probe["blocked_reasons"]),
                    counts=counts,
                    cleanup_status="succeeded",
                )
            resource = worker.resource_repository
            resource.add_pool(
                {
                    "pool_id": "android-devices",
                    "object_id": task.payload["device_profile"]["id"],
                    "target_id": snapshot["target"]["id"],
                    "tenant_id": binding.get("tenant_id", ""),
                    "project_id": binding.get("project_id", ""),
                    "dedicated_test_resource": True,
                }
            ) if not any(
                r["object_id"] == task.payload["device_profile"]["id"] for r in resource.pool()
            ) else None
            lease = resource.lease(
                "android-devices",
                task.run_id,
                {
                    "target_id": snapshot["target"]["id"],
                    "tenant_id": binding.get("tenant_id", ""),
                    "project_id": binding.get("project_id", ""),
                },
                int(data["timeout_seconds"]) + 60,
                object_id=task.payload["device_profile"]["id"],
            )
            session = AndroidSession(profile, secret_value(profile["device_secret_ref"]))
        else:
            options = {
                key: data[key] for key in ["capture_trace", "capture_video"] if data.get(key)
            }
            session = WebSession(data["chromium_version"], **options)

        deadline = monotonic() + max(
            0, (claimed.deadline_at - datetime.now(timezone.utc)).total_seconds()
        )
        requirements = task.payload.get("journey_fixture_plan", [])
        if requirements or any(action["action"] == "api_assert" for action in data["actions"]):
            api_resources = JourneyResources(
                worker.resource_repository,
                task.payload["context_snapshots"],
                requirements,
                context,
                task.run_id,
                deadline,
                redactor,
                should_stop=lambda: (
                    "cancelled" if repo.get_detail(task.run_id).cancel_requested_at else None
                ),
            )
            api_resources.prepare()
            context = api_resources.context.variables

        def stop():
            if api_resources:
                api_resources.check()
            if lease:
                worker.resource_repository.check_lease(lease)
            return bool(repo.get_detail(task.run_id).cancel_requested_at)

        def artifact(step_id, content):
            return worker._run_service.diagnostic_service.add_artifact(
                task.run_id,
                {
                    "step_id": step_id,
                    "content_type": "image/png",
                    "base64": __import__("base64").b64encode(content).decode(),
                    "synthetic_test_data": True,
                    "redaction_verified": True,
                },
            )

        result, cleanup, cases = execute_journey(
            data,
            session,
            context,
            stop=stop,
            artifact=artifact,
            remember_secret=redactor._collect,
            on_result=record_case,
            api_action=api_resources.assert_api if api_resources else None,
            deadline=monotonic()
            + max(0, (claimed.deadline_at - datetime.now(timezone.utc)).total_seconds()),
        )
        if hasattr(session, "take_artifacts"):
            for content_type, content in session.take_artifacts():
                try:
                    worker._run_service.diagnostic_service.add_artifact(
                        task.run_id,
                        {
                            "step_id": cases[-1].case_id if cases else None,
                            "content_type": content_type,
                            "base64": __import__("base64").b64encode(content).decode(),
                            "synthetic_test_data": True,
                            "redaction_verified": True,
                        },
                    )
                except Exception:
                    cleanup = "cleanup_failed"
        session = None
        if api_resources:
            cleanup = api_resources.close(cleanup)
        if lease and cleanup == "succeeded":
            try:
                worker.resource_repository.release_lease(lease)
                lease = None
            except Exception:
                cleanup = "needs_reconciliation"
        return repo.finish(
            task.run_id,
            claimed.attempt_id,
            RunStatus(result),
            "UI旅程结束；真实能力与业务范围见基线",
            counts=counts,
            cleanup_status=cleanup,
        )
    except Exception as exc:
        cleanup = "needs_reconciliation" if lease else "succeeded"
        if session:
            try:
                session.close()
            except Exception:
                cleanup = "cleanup_failed"
        session = None
        if api_resources:
            try:
                cleanup = api_resources.close(cleanup)
            except Exception:
                cleanup = "cleanup_failed"
        try:
            block_unexecuted(
                redactor.clean(str(exc) if isinstance(exc, ContextError) else type(exc).__name__)
            )
        except Exception:
            # 保留原执行/存储错误；不能因补全未执行记录再次失败而跳过终态。
            pass
        return repo.finish(
            task.run_id,
            claimed.attempt_id,
            RunStatus(
                getattr(
                    exc, "execution_status", "blocked" if isinstance(exc, ContextError) else "error"
                )
            ),
            redactor.clean(str(exc) if isinstance(exc, ContextError) else type(exc).__name__),
            counts=counts,
            cleanup_status=cleanup,
        )
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
        if lease and repo.get_detail(task.run_id).cleanup_status == "succeeded":
            try:
                worker.resource_repository.release_lease(lease)
            except Exception:
                pass

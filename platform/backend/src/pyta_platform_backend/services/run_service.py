"""run 业务服务层。"""

from copy import deepcopy
from typing import Optional

from fastapi import HTTPException, status

from pyta_platform_backend.repositories.management_repository import InMemoryManagementRepository
from pyta_platform_backend.repositories.run_repository import (
    InMemoryRunRepository,
    RunConflict,
    RunRecord,
)
from pyta_platform_backend.schemas.run import (
    CreateRunRequest,
    CreateRunResponse,
    ListRunsResponse,
    RunDetailResponse,
    UpdateRunStatusRequest,
)
from pyta_platform_backend.services.redaction import Redactor
from pyta_platform_backend.services.run_validation import load_definition, validate_live_payload
from pyta_platform_backend.workers.dispatcher import DispatchTask, MemoryRunDispatcher


class RunService:
    """run 服务。

    服务层负责串联“平台真源持久化”和“向 worker 投递任务”两个步骤。
    这样路由函数就能保持很薄，后续替换数据库或消息投递实现时也不会改 API 层。
    """

    def __init__(
        self,
        repository: InMemoryRunRepository,
        dispatcher: MemoryRunDispatcher,
        management_repository: Optional[InMemoryManagementRepository] = None,
        context_service=None,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher
        self._management_repository = management_repository
        self.context_service = context_service
        self.diagnostic_service = None

    @property
    def repository(self) -> InMemoryRunRepository:
        """暴露仓储给测试或诊断代码读取。"""

        return self._repository

    @property
    def dispatcher(self) -> MemoryRunDispatcher:
        """暴露投递器给测试或诊断代码读取。"""

        return self._dispatcher

    def create_run(self, payload: CreateRunRequest) -> CreateRunResponse:
        """创建 run 并投递到 worker。"""

        environment = self._resolve_environment(payload.environment_id)
        prepared_payload = self._prepare_run_request(payload, environment=environment)
        if payload.payload.get("execution_mode") == "evaluation":
            raise HTTPException(
                409,
                {
                    "code": "evaluation_execution_disabled",
                    "message": "新评估执行已禁用；历史报告仍可读取",
                },
            )
        if payload.payload.get("execution_mode") == "ui_journey":
            raise HTTPException(400, "UI旅程必须通过版本化入口提交")
        if payload.payload.get("run_definition", {}).get("metadata", {}).get("fixture_plan"):
            raise HTTPException(400, "fixture计划只能由已发布资产编译")
        if set(payload.payload) & {"asset_ref", "scenario_refs", "scenario_version_ref"}:
            raise HTTPException(400, "版本资产证据引用只能由平台编译生成")
        definition = payload.payload.get("run_definition", {})
        if definition.get("metadata", {}).get("business_database_plan") or any(
            case.get("metadata", {}).get("database_check")
            for case in definition.get("cases", []) + definition.get("cleanup_cases", [])
        ):
            raise HTTPException(400, "业务数据库核验只能由版本化资产编译")
        if "context_snapshots" in payload.payload:
            raise HTTPException(400, "上下文快照只能由平台配置生成")
        if self.context_service:
            try:
                prepared_payload.payload = self.context_service.prepare(
                    payload, prepared_payload.payload
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        return self._create_prepared(prepared_payload, environment.name if environment else None)

    def _create_prepared(self, prepared_payload, environment_name, idempotency_key=None):
        try:
            load_definition(prepared_payload.payload)
        except (ValueError, TypeError, OSError) as exc:
            raise HTTPException(400, Redactor(prepared_payload.payload).clean(str(exc))) from exc
        record: RunRecord = self._repository.create_pending_run(
            prepared_payload,
            environment_name=environment_name,
            idempotency_key=idempotency_key,
        )
        self._dispatcher.dispatch(
            DispatchTask(
                run_id=record.run_id,
                suite_id=record.suite_id,
                trigger_source=record.trigger_source,
                requested_by=record.requested_by,
                payload=deepcopy(prepared_payload.payload),
                dispatched_at=record.created_at,
            )
        )
        return CreateRunResponse(
            run_id=record.run_id,
            status=record.status,
            dispatch_channel=self._dispatcher.channel_name,
            environment_id=record.environment_id,
            environment_name=record.environment_name,
        )

    def list_runs(self, limit: int = 20, offset: int = 0, **filters) -> ListRunsResponse:
        """列出 run 列表。"""

        if self.diagnostic_service and any(value is not None for value in filters.values()):
            return self.diagnostic_service.filtered_runs(limit=limit, offset=offset, **filters)
        safe_limit = max(1, min(limit, 200))
        safe_offset = max(0, offset)
        return self._repository.list_runs(limit=safe_limit, offset=safe_offset)

    def get_run_detail(self, run_id: str) -> RunDetailResponse:
        """按 run_id 查询详情。"""

        detail = self._repository.get_detail(run_id)
        if detail is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run 不存在: {run_id}",
            )
        return detail

    def update_run_status(self, run_id: str, payload: UpdateRunStatusRequest) -> RunDetailResponse:
        """更新 run 状态。"""

        try:
            detail = self._repository.update_status(run_id=run_id, payload=payload)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, f"run 不存在: {run_id}") from exc
        if detail is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run 不存在: {run_id}",
            )
        return detail

    def _resolve_environment(self, environment_id: Optional[str]):
        """解析 environment_id，并返回对应环境记录。"""

        if not environment_id:
            return None
        if self._management_repository is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前 run service 未接入 environment 仓储，无法解析 environment_id",
            )

        environment = self._management_repository.get_environment_by_id(environment_id)
        if environment is not None:
            return environment

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"environment 不存在: {environment_id}",
        )

    @staticmethod
    def _prepare_run_request(
        payload: CreateRunRequest,
        *,
        environment,
    ) -> CreateRunRequest:
        """把 environment 快照写入运行时 payload。"""

        runtime_payload = deepcopy(payload.payload)
        if environment is not None:
            runtime_payload["environment"] = {
                "id": environment.id,
                "name": environment.name,
                "base_url": environment.base_url,
                "auth_mode": environment.auth_mode,
                "variables": deepcopy(environment.variables),
            }

        if hasattr(payload, "model_copy"):
            return payload.model_copy(update={"payload": runtime_payload}, deep=True)
        return payload.copy(update={"payload": runtime_payload}, deep=True)

    def cancel_run(self, run_id):
        try:
            return self._repository.cancel(run_id)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, f"run 不存在: {run_id}") from exc

    def ensure_resumable(self, run_id):
        """Historical imports and simulated evidence are read-only, including queued rows."""
        record = self._repository.get_by_id(run_id)
        if record is None:
            return self.get_run_detail(run_id)
        if record.execution.get("migration", {}).get("do_not_resume"):
            raise HTTPException(
                409, "historical_run_read_only: 迁入运行仅供历史查询，不允许恢复或复跑"
            )
        if record.payload.get("execution_mode") == "evaluation":
            raise HTTPException(409, "evaluation_execution_disabled: 新评估执行已禁用")
        try:
            validate_live_payload(record.payload)
        except (ValueError, TypeError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return self.get_run_detail(run_id)

    def rerun(self, run_id, failed_only=False):
        previous = self.ensure_resumable(run_id)
        if previous.status.value in {"queued", "running"}:
            raise HTTPException(409, "原运行尚未结束，不能用复跑并发重放")
        payload = deepcopy(previous.payload)
        payload["original_run_id"] = run_id
        if failed_only:
            scopes = {
                case.get("metadata", {}).get("scope_id")
                for case in previous.results
                if case.get("phase") != "cleanup" and case["status"] not in {"passed", "skipped"}
            } - {None}
            if scopes:
                definition = payload["run_definition"]
                for field in ["cases", "cleanup_cases"]:
                    definition[field] = [
                        case
                        for case in definition.get(field, [])
                        if case.get("metadata", {}).get("scope_id") in scopes
                    ]
                for field in ["scopes", "fixture_plan"]:
                    definition.setdefault("metadata", {})[field] = {
                        key: value
                        for key, value in definition.get("metadata", {}).get(field, {}).items()
                        if key in scopes
                    }
                snapshots = {
                    key: value
                    for key, value in payload.get("context_snapshots", {}).items()
                    if key in scopes
                }
                if snapshots:
                    snapshots["default"] = next(iter(snapshots.values()))
                payload["context_snapshots"] = snapshots
                selected = {
                    (
                        case.get("metadata", {}).get("scenario_ref", {}).get("id"),
                        case.get("metadata", {}).get("scenario_ref", {}).get("version"),
                    )
                    for case in definition["cases"]
                }
                payload["scenario_refs"] = [
                    ref
                    for ref in payload.get("scenario_refs", [])
                    if (ref["id"], ref["version"]) in selected
                ]
                payload["rerun_selection"] = {
                    "failed_only": True,
                    "scope_ids": sorted(scopes),
                    "partial": True,
                }
            elif previous.results and all(
                case["status"] in {"passed", "skipped"} for case in previous.results
            ):
                raise HTTPException(400, "没有失败场景可复跑")
            else:
                payload["rerun_selection"] = {
                    "failed_only_requested": True,
                    "partial": False,
                    "note": "inline无场景边界，完整重建上下文",
                }
        if self.context_service:
            for snapshot in payload.get("context_snapshots", {}).values():
                for kind, field in [
                    ("targets", "target"),
                    ("identity-profiles", "identity"),
                    ("context-bindings", "binding"),
                ]:
                    if snapshot.get(field):
                        self.context_service.get(kind, snapshot[field]["id"])
        return self._create_prepared(
            CreateRunRequest(
                suite_id=previous.suite_id,
                environment_id=previous.environment_id,
                trigger_source="rerun",
                requested_by=previous.requested_by,
                payload=payload,
            ),
            previous.environment_name,
        )

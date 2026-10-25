"""run 相关接口。"""

from fastapi import APIRouter, status

from pyta_platform_backend.schemas.run import (
    CreateRunRequest,
    CreateRunResponse,
    ListRunsResponse,
    RunDetailResponse,
    UpdateRunStatusRequest,
)
from pyta_platform_backend.services.run_service import RunService


def create_runs_router(run_service: RunService) -> APIRouter:
    """注册 run 路由。

    这里故意只放“创建 run”入口，用来体现平台的第一阶段职责：
    API 收到请求后创建 run 记录，并把执行任务交给 worker。
    """

    router = APIRouter(prefix="/runs", tags=["runs"])

    @router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
    def create_run(payload: CreateRunRequest) -> CreateRunResponse:
        """创建 run 并投递到 worker。"""

        return run_service.create_run(payload)

    @router.get("", response_model=ListRunsResponse, status_code=status.HTTP_200_OK)
    def list_runs(
        limit: int = 20,
        offset: int = 0,
        environment_id: str = None,
        target_id: str = None,
        transport_mode: str = None,
        scenario_id: str = None,
        scenario_version: int = None,
        status: str = None,
        category: str = None,
        since: str = None,
        until: str = None,
    ) -> ListRunsResponse:
        """返回 run 列表。

        这里优先给结果页和仪表盘提供真实数据来源。
        """

        return run_service.list_runs(
            limit=limit,
            offset=offset,
            environment_id=environment_id,
            target_id=target_id,
            transport_mode=transport_mode,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            status=status,
            category=category,
            since=since,
            until=until,
        )

    @router.get("/{run_id}", response_model=RunDetailResponse, status_code=status.HTTP_200_OK)
    def get_run_detail(run_id: str) -> RunDetailResponse:
        """返回单个 run 详情。"""

        return run_service.get_run_detail(run_id)

    @router.patch(
        "/{run_id}/status",
        response_model=RunDetailResponse,
        status_code=status.HTTP_200_OK,
    )
    def update_run_status(run_id: str, payload: UpdateRunStatusRequest) -> RunDetailResponse:
        """更新 run 状态。

        这个接口主要给 worker 或调度器回写状态使用。
        """

        return run_service.update_run_status(run_id=run_id, payload=payload)

    @router.post("/{run_id}/cancel", response_model=RunDetailResponse)
    def cancel_run(run_id: str) -> RunDetailResponse:
        return run_service.cancel_run(run_id)

    @router.get("/{run_id}/results", response_model=RunDetailResponse)
    def get_results(run_id: str) -> RunDetailResponse:
        return run_service.get_run_detail(run_id)

    @router.get("/{run_id}/steps/{step_id}/trace")
    def get_trace(run_id: str, step_id: str):
        from fastapi import HTTPException

        record = next(
            (
                case
                for case in run_service.get_run_detail(run_id).results
                if case["case_id"] == step_id
            ),
            None,
        )
        if record is None:
            raise HTTPException(404, "步骤结果不存在")
        return record

    @router.get("/{run_id}/export", response_model=RunDetailResponse)
    def export_run(run_id: str) -> RunDetailResponse:
        return run_service.get_run_detail(run_id)

    @router.post("/{run_id}/rerun", response_model=CreateRunResponse, status_code=202)
    def rerun(run_id: str, failed_only: bool = False) -> CreateRunResponse:
        return run_service.rerun(run_id, failed_only)

    return router

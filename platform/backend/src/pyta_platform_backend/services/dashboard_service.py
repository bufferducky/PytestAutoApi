"""仪表盘业务服务。

这个服务先只做一件事：
把 run 仓储里的真实状态，整理成首页能够直接消费的结构。

之所以单独做 service，而不是在路由里拼字典，是为了后续加更多统计项时，
仍然能保持 API 层足够薄。
"""

from zoneinfo import ZoneInfo

from pyta_platform_backend.repositories.run_repository import InMemoryRunRepository
from pyta_platform_backend.schemas.dashboard import (
    DashboardMetricResponse,
    DashboardOverviewResponse,
    DashboardRecentRunResponse,
)
from pyta_platform_backend.schemas.run import RunStatus


class DashboardService:
    """首页聚合服务。"""

    def __init__(self, repository: InMemoryRunRepository) -> None:
        self._repository = repository

    def get_overview(self) -> DashboardOverviewResponse:
        """构造首页总览。

        统计仅聚合真实执行，最近运行保留历史模式标识。
        """

        records = self._repository.list_runs(limit=5, offset=0)
        stats = self._repository.live_stats()

        metrics = [
            DashboardMetricResponse(
                key="runs",
                label="累计运行",
                value=str(stats["total"]),
                description="真实测试运行总数，不含迁入演示历史",
                trend=f"最近 {len(records.items)} 条可在结果页查看",
            ),
            DashboardMetricResponse(
                key="queued",
                label="排队中",
                value=str(stats["queued"]),
                description="已经创建但尚未开始执行的 run",
                trend="等待执行器处理",
            ),
            DashboardMetricResponse(
                key="running",
                label="执行中",
                value=str(stats["running"]),
                description="当前仍在 worker 中运行的 run",
                trend="刷新可查看最新执行状态",
            ),
            DashboardMetricResponse(
                key="failed",
                label="失败数",
                value=str(stats["failed"]),
                description="用于快速发现最近需要优先排查的问题",
                trend="失败记录可在执行结果中查看",
            ),
        ]

        recent_runs = [
            DashboardRecentRunResponse(
                id=item.run_id,
                name=f"运行 {item.run_id[:8]}",
                target=item.suite_id,
                status=self._map_run_status(item.status),
                started_at=self._format_time(item.started_at or item.created_at),
                duration=self._format_duration(item.created_at, item.finished_at),
                starter=item.requested_by,
                raw_status=item.status.value,
                transport_mode=item.transport_mode,
                validation_scope=item.validation_scope,
            )
            for item in records.items[:3]
        ]

        return DashboardOverviewResponse(
            metrics=metrics,
            focus_items=[],
            recent_runs=recent_runs,
        )

    @staticmethod
    def _map_run_status(status: RunStatus) -> str:
        """把后端原始状态映射到首页更易读的展示状态。"""

        if status == RunStatus.RUNNING:
            return "running"
        if status == RunStatus.FAILED:
            return "warning"
        if status == RunStatus.SUCCEEDED:
            return "success"
        return "running" if status == RunStatus.QUEUED else "warning"

    @staticmethod
    def _format_time(value) -> str:
        """把 datetime 转成前端可直接展示的字符串。"""

        return value.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def _format_duration(cls, created_at, finished_at) -> str:
        """把 run 耗时格式化为简单文案。

        当前没有真实 worker 开始/结束时间链路，所以第一阶段先退化为：
        - 已完成：按 created_at 到 finished_at 计算
        - 未完成：展示“执行中”
        """

        if finished_at is None:
            return "执行中"
        seconds = int((finished_at - created_at).total_seconds())
        minutes, remain_seconds = divmod(seconds, 60)
        return f"{minutes}m {remain_seconds}s"

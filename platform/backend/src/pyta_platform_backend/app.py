"""FastAPI 应用装配入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from pyta_platform_backend.api.router import register_routes
from pyta_platform_backend.api.routes.assets import create_assets_router
from pyta_platform_backend.api.routes.context import create_context_router
from pyta_platform_backend.api.routes.diagnostics import create_diagnostics_router
from pyta_platform_backend.api.routes.evaluations import create_evaluations_router
from pyta_platform_backend.api.routes.journeys import create_journeys_router
from pyta_platform_backend.api.routes.resources import create_resources_router
from pyta_platform_backend.api.routes.schedules import create_schedules_router
from pyta_platform_backend.config import BackendSettings
from pyta_platform_backend.repositories.artifact_repository import ArtifactRepository
from pyta_platform_backend.repositories.asset_repository import AssetRepository
from pyta_platform_backend.repositories.context_repository import ContextRepository
from pyta_platform_backend.repositories.management_repository import (
    InMemoryManagementRepository,
    SqlManagementRepository,
)
from pyta_platform_backend.repositories.resource_repository import ResourceRepository
from pyta_platform_backend.repositories.run_repository import (
    SqlRunRepository,
)
from pyta_platform_backend.repositories.schedule_repository import ScheduleRepository
from pyta_platform_backend.services.asset_service import AssetService
from pyta_platform_backend.services.context_service import ContextService
from pyta_platform_backend.services.dashboard_service import DashboardService
from pyta_platform_backend.services.demo_suite_service import DemoSuiteService
from pyta_platform_backend.services.diagnostic_service import DiagnosticService
from pyta_platform_backend.services.evaluation_service import EvaluationService
from pyta_platform_backend.services.journey_service import JourneyService
from pyta_platform_backend.services.management_service import ManagementService
from pyta_platform_backend.services.notification_service import NotificationService
from pyta_platform_backend.services.release_service import ReleaseService
from pyta_platform_backend.services.resource_service import ResourceService
from pyta_platform_backend.services.run_service import RunService
from pyta_platform_backend.services.schedule_service import ScheduleHost, ScheduleService
from pyta_platform_backend.services.worker_control_service import WorkerControlService
from pyta_platform_backend.workers.dispatcher import PersistentRunDispatcher
from pyta_platform_backend.workers.host import WorkerHost
from pyta_platform_backend.workers.run_worker import RunWorker


def build_default_run_service(
    settings: BackendSettings,
    management_repository: InMemoryManagementRepository = None,
) -> RunService:
    """组装默认的 run service。

    这里明确体现第一阶段的边界：
    - API 进程只负责“写入平台主真源” + “投递给 worker”
    - 真正的长任务执行不发生在 FastAPI 路由里
    """

    repository = SqlRunRepository(database_path=settings.resolve_database_url())
    dispatcher = PersistentRunDispatcher(repository)
    return RunService(
        repository=repository,
        dispatcher=dispatcher,
        management_repository=management_repository,
    )


def create_app(
    settings: BackendSettings = None,
    run_service: RunService = None,
) -> FastAPI:
    """创建 FastAPI 应用实例。

    通过显式注入 ``settings`` / ``run_service``，
    可以让测试、未来的依赖替换和真实部署装配都保持清晰。
    """

    resolved_settings = settings or BackendSettings.from_env()
    shared_management_repository = SqlManagementRepository(
        database_path=resolved_settings.resolve_database_url()
    )
    resolved_run_service = run_service or build_default_run_service(
        resolved_settings,
        management_repository=shared_management_repository,
    )
    context_service = ContextService(
        ContextRepository(resolved_settings.resolve_database_url()),
        shared_management_repository,
        resolved_run_service.repository,
    )
    resolved_run_service.context_service = context_service
    resolved_dashboard_service = DashboardService(repository=resolved_run_service.repository)
    # 退役接口只保留空列表与 410 响应，不再持有执行或仓储依赖。
    resolved_demo_suite_service = DemoSuiteService()
    resolved_management_service = ManagementService(
        repository=shared_management_repository,
        run_repository=resolved_run_service.repository,
    )
    resolved_management_service.context_service = context_service
    resolved_worker_runner = RunWorker(
        dispatcher=resolved_run_service.dispatcher,
        run_service=resolved_run_service,
    )
    worker_host = WorkerHost(
        resolved_worker_runner,
        resolved_run_service.repository,
        resolved_settings.resolve_database_url(),
    )
    resource_service = ResourceService(
        ResourceRepository(resolved_settings.resolve_database_url()), resolved_run_service
    )
    resolved_worker_runner.resource_repository = resource_service.repository

    def recover_resources():
        if hasattr(resolved_run_service.dispatcher, "recover"):
            resolved_run_service.dispatcher.recover()
        resource_service.repository.reconcile(
            {r.run_id for r in resolved_run_service.repository.list_queued_records()}
        )

    worker_host.recovery_callback = recover_resources
    resolved_worker_control_service = WorkerControlService(
        worker_runner=resolved_worker_runner,
        run_service=resolved_run_service,
        worker_host=worker_host,
    )

    @asynccontextmanager
    async def lifespan(app):
        worker_host.start()
        try:
            schedule_host.start()
            yield
        finally:
            schedule_host.stop()
            worker_host.stop()

    app = FastAPI(
        lifespan=lifespan,
        title=resolved_settings.app_name,
        debug=resolved_settings.debug,
        version=resolved_settings.app_version,
    )

    # 把核心对象挂到 app.state，方便后续在启动事件、管理接口或测试里复用。
    asset_service = AssetService(
        AssetRepository(resolved_settings.resolve_database_url()),
        resolved_run_service,
        context_service,
    )
    asset_service.resources = resource_service
    app.state.resource_service = resource_service
    database_url = resolved_settings.resolve_database_url()
    artifact_root = resolved_settings.resolve_artifact_root()
    diagnostic_service = DiagnosticService(
        resolved_run_service, resource_service, ArtifactRepository(database_url, artifact_root)
    )
    resolved_run_service.diagnostic_service = diagnostic_service
    app.state.diagnostic_service = diagnostic_service
    schedule_repository = ScheduleRepository(database_url)
    schedule_service = ScheduleService(
        schedule_repository,
        asset_service,
        resolved_run_service,
        worker_host,
        shared_management_repository,
    )
    schedule_service.resources = resource_service
    schedule_host = ScheduleHost(
        schedule_service, resolved_settings.scheduler_poll_interval_seconds
    )
    release_service = ReleaseService(schedule_repository, resolved_run_service, asset_service)
    journey_service = JourneyService(
        resource_service.repository,
        resolved_run_service,
        context_service,
        resource_service,
        diagnostic_service,
    )
    evaluation_service = EvaluationService(resource_service.repository, resolved_run_service)
    resolved_run_service.evaluation_service = evaluation_service
    app.state.evaluation_service = evaluation_service
    release_service.journeys = journey_service
    app.state.journey_service = journey_service
    app.state.schedule_service = schedule_service
    app.state.schedule_host = schedule_host
    app.state.release_service = release_service
    app.state.notification_service = NotificationService(schedule_repository)
    worker_host.on_run_finished = app.state.notification_service.notify_finished
    app.state.asset_service = asset_service
    app.state.context_service = context_service
    app.state.worker_host = worker_host
    app.state.settings = resolved_settings
    app.state.run_service = resolved_run_service
    app.state.dashboard_service = resolved_dashboard_service
    app.state.demo_suite_service = resolved_demo_suite_service
    app.state.management_service = resolved_management_service
    app.state.worker_runner = resolved_worker_runner
    app.state.worker_control_service = resolved_worker_control_service

    register_routes(
        app=app,
        settings=resolved_settings,
        run_service=resolved_run_service,
        dashboard_service=resolved_dashboard_service,
        demo_suite_service=resolved_demo_suite_service,
        management_service=resolved_management_service,
        worker_control_service=resolved_worker_control_service,
    )
    app.include_router(create_context_router(context_service, resolved_settings.api_prefix))
    app.include_router(create_assets_router(asset_service, resolved_settings.api_prefix))
    app.include_router(create_resources_router(resource_service, resolved_settings.api_prefix))
    app.include_router(create_diagnostics_router(diagnostic_service, resolved_settings.api_prefix))
    app.include_router(
        create_schedules_router(schedule_service, release_service, resolved_settings.api_prefix)
    )
    app.include_router(create_journeys_router(journey_service, resolved_settings.api_prefix))
    app.include_router(create_evaluations_router(evaluation_service, resolved_settings.api_prefix))
    return app

"""平台后端骨架的最小测试。"""

import importlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fake_fastapi import install_fake_fastapi

_TEST_HTTP_BASE = ""


@pytest.fixture(autouse=True)
def local_http():
    global _TEST_HTTP_BASE

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"code":200}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _TEST_HTTP_BASE = f"http://127.0.0.1:{server.server_port}"
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _create_test_app(module, settings):
    app = module.create_app(settings=settings)
    schema = importlib.import_module("pyta_platform_backend.schemas.management")
    environments = app.state.management_service.list_environments()
    existing = next((row for row in environments if row.name == "local-test"), None)
    environment = existing or app.state.management_service.create_environment(
        schema.CreateEnvironmentRequest(
            name="local-test", base_url=_TEST_HTTP_BASE, auth_mode="none"
        )
    )
    app.state.test_environment_id = environment.id
    return app


def _valid_payload(**extra):
    return {
        "execution_mode": "standard_run",
        "transport_mode": "live",
        "run_definition": {
            "cases": [
                {
                    "case_id": "check",
                    "title": "check",
                    "request": {"url": _TEST_HTTP_BASE},
                    "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                }
            ]
        },
        **extra,
    }


def _reload_backend_modules(monkeypatch):
    """在注入 fake fastapi 后重新加载后端模块。"""

    install_fake_fastapi(monkeypatch)

    for module_name in list(sys.modules):
        if module_name == "pyta_platform_backend" or module_name.startswith(
            "pyta_platform_backend."
        ):
            sys.modules.pop(module_name, None)

    app_module = importlib.import_module("pyta_platform_backend.app")
    config_module = importlib.import_module("pyta_platform_backend.config")
    run_schema_module = importlib.import_module("pyta_platform_backend.schemas.run")
    return app_module, config_module, run_schema_module


def _find_route(app, path: str, method: str):
    """按路径和方法查找注册后的路由。"""

    for route in app.routes:
        if route.path == path and method in route.methods:
            return route
    raise AssertionError(f"未找到路由: {method} {path}")


def test_create_app_registers_routes_and_health_endpoint(monkeypatch):
    """应用创建后应注册核心路由，并能返回最小健康信息。"""

    app_module, config_module, _ = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(
        app_name="Platform Backend Test",
        app_env="test",
        api_prefix="/api/test",
    )

    app = _create_test_app(app_module, settings)

    assert app.title == "Platform Backend Test"
    assert app.state.settings.app_env == "test"
    assert app.state.scheduler.poll_interval_seconds == settings.scheduler_poll_interval_seconds
    assert app.state.dashboard_service is not None
    assert app.state.management_service is not None

    cases_route = _find_route(app, "/api/test/cases", "GET")
    dashboard_route = _find_route(app, "/api/test/dashboard/overview", "GET")
    demo_suites_route = _find_route(app, "/api/test/demo-suites", "GET")
    environments_route = _find_route(app, "/api/test/environments", "GET")
    environments_create_route = _find_route(app, "/api/test/environments", "POST")
    environments_detail_route = _find_route(app, "/api/test/environments/{environment_id}", "GET")
    environments_patch_route = _find_route(app, "/api/test/environments/{environment_id}", "PATCH")
    environments_delete_route = _find_route(
        app,
        "/api/test/environments/{environment_id}",
        "DELETE",
    )
    live_route = _find_route(app, "/api/test/health/live", "GET")
    runs_route = _find_route(app, "/api/test/runs", "POST")
    schedules_route = _find_route(app, "/api/test/schedules", "GET")
    suites_route = _find_route(app, "/api/test/suites", "GET")
    worker_route = _find_route(app, "/api/test/worker/run-next", "POST")
    worker_run_by_id_route = _find_route(
        app,
        "/api/test/worker/runs/{run_id}/execute",
        "POST",
    )

    cases_payload = cases_route.endpoint()
    overview_payload = dashboard_route.endpoint()
    demo_suites_payload = demo_suites_route.endpoint()
    environments_payload = environments_route.endpoint()
    health_payload = live_route.endpoint()
    schedules_payload = schedules_route.endpoint()
    suites_payload = suites_route.endpoint()
    assert health_payload.status == "ok"
    assert health_payload.environment == "test"
    assert cases_payload == []
    assert overview_payload.metrics
    assert demo_suites_payload.items == []
    assert environments_payload
    assert environments_create_route.status_code == 201
    assert environments_detail_route.status_code == 200
    assert environments_patch_route.status_code == 200
    assert environments_delete_route.status_code == 200
    assert runs_route.status_code == 202
    assert schedules_payload == []
    assert suites_payload == []
    assert worker_route.status_code == 202
    assert worker_run_by_id_route.status_code == 202


def test_create_run_endpoint_only_persists_and_dispatches(monkeypatch):
    """创建 run 的路由只负责写入主真源并投递 worker。"""

    app_module, config_module, run_schema_module = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(
        app_env="test",
        run_dispatch_channel="test-memory-worker",
    )
    app = _create_test_app(app_module, settings)

    create_run_route = _find_route(app, "/api/v1/runs", "POST")
    payload = run_schema_module.CreateRunRequest(
        suite_id="smoke-suite",
        environment_id=app.state.test_environment_id,
        trigger_source="manual",
        requested_by="tester",
        payload=_valid_payload(retry=0),
    )

    response = create_run_route.endpoint(payload)

    stored_record = app.state.run_service.repository.get_by_id(response.run_id)
    dispatched_task = app.state.run_service.dispatcher.dispatched_tasks[0]

    assert stored_record is not None
    assert stored_record.status.value == "queued"
    assert stored_record.run_id == response.run_id
    assert stored_record.environment_id == app.state.test_environment_id
    assert stored_record.environment_name == "local-test"
    assert stored_record.payload["environment"]["base_url"]
    assert dispatched_task.run_id == response.run_id
    assert response.dispatch_channel == "mysql-outbox"
    assert response.environment_id == app.state.test_environment_id
    assert response.environment_name == "local-test"
    assert dispatched_task.dispatched_at == stored_record.created_at


def test_runs_routes_support_list_detail_and_status_update(monkeypatch):
    """run 链路应支持结果页第一阶段最需要的三个动作。"""

    app_module, config_module, run_schema_module = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(app_env="test")
    app = _create_test_app(app_module, settings)

    create_run_route = _find_route(app, "/api/v1/runs", "POST")
    list_runs_route = _find_route(app, "/api/v1/runs", "GET")
    detail_route = _find_route(app, "/api/v1/runs/{run_id}", "GET")
    patch_route = _find_route(app, "/api/v1/runs/{run_id}/status", "PATCH")

    created = create_run_route.endpoint(
        run_schema_module.CreateRunRequest(
            suite_id="nightly-suite",
            environment_id=app.state.test_environment_id,
            trigger_source="scheduler",
            requested_by="system",
            payload=_valid_payload(tenant="demo"),
        )
    )

    list_payload = list_runs_route.endpoint(limit=20, offset=0)
    assert list_payload.total == 1
    assert list_payload.items[0].run_id == created.run_id
    assert list_payload.items[0].environment_id == app.state.test_environment_id
    assert list_payload.items[0].environment_name == "local-test"
    assert list_payload.items[0].status.value == "queued"

    detail_payload = detail_route.endpoint(created.run_id)
    assert detail_payload.run_id == created.run_id
    assert detail_payload.environment_name == "local-test"
    assert detail_payload.payload["tenant"] == "demo"
    assert detail_payload.payload["environment"]["id"] == app.state.test_environment_id

    patched = patch_route.endpoint(
        created.run_id,
        run_schema_module.UpdateRunStatusRequest(
            status=run_schema_module.RunStatus.RUNNING,
            status_message="worker started",
            expected_version=detail_payload.version,
        ),
    )
    assert patched.status.value == "running"
    assert patched.attempt_id is not None


def test_create_run_rejects_unknown_environment_id(monkeypatch):
    """run 创建时应校验 environment_id，而不是把错误 ID 写进主真源。"""

    app_module, config_module, run_schema_module = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(app_env="test")
    app = _create_test_app(app_module, settings)

    create_run_route = _find_route(app, "/api/v1/runs", "POST")

    try:
        create_run_route.endpoint(
            run_schema_module.CreateRunRequest(
                suite_id="smoke-suite",
                environment_id="env-missing",
                trigger_source="manual",
                requested_by="tester",
                payload=_valid_payload(),
            )
        )
    except Exception as exc:
        assert exc.status_code == 404
        assert "environment 不存在" in exc.detail
    else:  # pragma: no cover - 测试断言保护
        raise AssertionError("未知 environment_id 应被拒绝")


def test_memory_worker_runner_can_consume_dispatched_task(monkeypatch):
    """最小 worker 应能消费 dispatcher 中的任务并回写成功状态。"""

    app_module, config_module, run_schema_module = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(app_env="test")
    app = _create_test_app(app_module, settings)

    created = app.state.run_service.create_run(
        run_schema_module.CreateRunRequest(
            suite_id="smoke-worker-suite",
            trigger_source="manual",
            requested_by="tester",
            payload=_valid_payload(tenant="demo"),
        )
    )
    detail = app.state.worker_runner.run_next()

    assert detail is not None
    assert detail.run_id == created.run_id
    assert detail.status.value == "succeeded"
    assert "standard run executed" in (detail.status_message or "")
    assert app.state.run_service.dispatcher.dispatched_tasks == []


def test_memory_worker_runner_marks_run_error_when_handler_raises(monkeypatch):
    """worker 执行异常时应把 run 回写为 error，而不是静默吞掉。"""

    app_module, config_module, run_schema_module = _reload_backend_modules(monkeypatch)
    runner_module = importlib.import_module("pyta_platform_backend.workers.runner")
    settings = config_module.BackendSettings(app_env="test")
    app = _create_test_app(app_module, settings)

    app.state.run_service.create_run(
        run_schema_module.CreateRunRequest(
            suite_id="boom-suite",
            trigger_source="manual",
            requested_by="tester",
            payload=_valid_payload(),
        )
    )
    broken_runner = runner_module.MemoryWorkerRunner(
        dispatcher=app.state.run_service.dispatcher,
        run_service=app.state.run_service,
        handler=lambda task: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    detail = broken_runner.run_next()

    assert detail is not None
    assert detail.status.value == "error"
    assert detail.status_message == "boom"


def test_legacy_execution_rejects_simulated_responses(monkeypatch):
    module, config, schema = _reload_backend_modules(monkeypatch)
    app = _create_test_app(module, config.BackendSettings(app_env="test"))
    with pytest.raises(Exception) as exc:
        app.state.run_service.create_run(
            schema.CreateRunRequest(
                suite_id="legacy",
                payload={
                    "execution_mode": "legacy_yaml",
                    "transport_mode": "mock",
                    "legacy_yaml_path": "data/Login/login.yaml",
                    "mock_case_responses": {},
                },
            )
        )
    assert exc.value.status_code == 400
    assert app.state.run_service.list_runs().total == 0


def test_management_catalog_does_not_seed_static_samples(monkeypatch):
    module, config, _ = _reload_backend_modules(monkeypatch)
    app = _create_test_app(module, config.BackendSettings(app_env="test"))
    for path in ["cases", "suites", "schedules"]:
        assert _find_route(app, "/api/v1/" + path, "GET").endpoint() == []
    assert app.state.asset_service.list("scenarios") == []
    assert app.state.asset_service.list("suites") == []


def test_environment_route_can_create_environment_and_reject_duplicate_name(monkeypatch):
    """环境接口应支持新增，并阻止重复名称覆盖目录。"""

    app_module, config_module, _ = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(app_env="test")
    app = _create_test_app(app_module, settings)

    create_environment_route = _find_route(app, "/api/v1/environments", "POST")
    list_environments_route = _find_route(app, "/api/v1/environments", "GET")
    management_schema_module = importlib.import_module("pyta_platform_backend.schemas.management")

    created = create_environment_route.endpoint(
        management_schema_module.CreateEnvironmentRequest(
            name="预发联调环境",
            base_url="https://staging.example.com/",
            auth_mode="Cookie + 单点登录",
            status="draft",
        )
    )

    assert created.name == "预发联调环境"
    assert created.base_url == "https://staging.example.com"
    assert created.variables == {}
    listed = list_environments_route.endpoint()
    assert any(item.id == created.id for item in listed)

    try:
        create_environment_route.endpoint(
            management_schema_module.CreateEnvironmentRequest(
                name="预发联调环境",
                base_url="https://another.example.com",
                auth_mode="Token",
                status="online",
            )
        )
    except Exception as exc:
        assert exc.status_code == 409
        assert "环境名称已存在" in exc.detail
    else:  # pragma: no cover - 测试断言保护
        raise AssertionError("重复环境名称应被拒绝")


def test_environment_routes_support_detail_update_and_delete(monkeypatch):
    """环境资源应具备 detail / patch / delete 完整闭环。"""

    app_module, config_module, _ = _reload_backend_modules(monkeypatch)
    settings = config_module.BackendSettings(app_env="test")
    app = _create_test_app(app_module, settings)

    create_environment_route = _find_route(app, "/api/v1/environments", "POST")
    detail_environment_route = _find_route(app, "/api/v1/environments/{environment_id}", "GET")
    patch_environment_route = _find_route(app, "/api/v1/environments/{environment_id}", "PATCH")
    delete_environment_route = _find_route(app, "/api/v1/environments/{environment_id}", "DELETE")
    list_environments_route = _find_route(app, "/api/v1/environments", "GET")
    management_schema_module = importlib.import_module("pyta_platform_backend.schemas.management")

    created = create_environment_route.endpoint(
        management_schema_module.CreateEnvironmentRequest(
            name="灰度环境",
            base_url="https://gray.example.com",
            auth_mode="Token + Header",
            status="draft",
            variables={"tenant": "gray"},
        )
    )
    detail = detail_environment_route.endpoint(created.id)
    assert detail.variables == {"tenant": "gray"}

    updated = patch_environment_route.endpoint(
        created.id,
        management_schema_module.UpdateEnvironmentRequest(
            expected_revision=detail.revision,
            name="灰度环境-已启用",
            status="online",
        ),
    )
    assert updated.name == "灰度环境-已启用"
    assert updated.status == "online"
    assert updated.base_url == "https://gray.example.com"
    assert updated.variables == {"tenant": "gray"}

    deleted = delete_environment_route.endpoint(created.id)
    assert deleted.name == "灰度环境-已启用"
    listed = list_environments_route.endpoint()
    assert all(item.id != created.id for item in listed)

    try:
        detail_environment_route.endpoint(created.id)
    except Exception as exc:
        assert exc.status_code == 404
    else:  # pragma: no cover - 测试断言保护
        raise AssertionError("删除后的环境详情查询应返回 404")


def test_demo_routes_are_retired_without_creating_runs(monkeypatch):
    module, config, _ = _reload_backend_modules(monkeypatch)
    app = _create_test_app(module, config.BackendSettings(app_env="test"))
    assert _find_route(app, "/api/v1/demo-suites", "GET").endpoint().items == []
    schema = importlib.import_module("pyta_platform_backend.schemas.demo_suite")
    with pytest.raises(Exception) as exc:
        _find_route(app, "/api/v1/demo-suites/{suite_id}/runs", "POST").endpoint(
            "demo-login-auth", schema.CreateDemoSuiteRunRequest(mode="live")
        )
    assert exc.value.status_code == 410
    assert app.state.run_service.list_runs().total == 0


def test_worker_route_prioritizes_specific_real_run(monkeypatch):
    module, config, schema = _reload_backend_modules(monkeypatch)
    app = _create_test_app(module, config.BackendSettings(app_env="test"))
    first, second = [
        app.state.run_service.create_run(
            schema.CreateRunRequest(suite_id="real-run", payload=_valid_payload())
        )
        for _ in range(2)
    ]
    queued = _find_route(app, "/api/v1/worker/runs/{run_id}/execute", "POST").endpoint(
        second.run_id
    )
    assert queued.status.value == "queued"
    executed = app.state.worker_runner.run_next()
    assert executed.run_id == second.run_id and executed.status.value == "succeeded"
    assert app.state.run_service.get_run_detail(first.run_id).status.value == "queued"


def test_sqlite_state_persists_runs_and_environments_across_app_recreation(monkeypatch, tmp_path):
    """轻量持久化应让环境和 run 在重启后仍可读取。"""

    app_module, config_module, run_schema_module = _reload_backend_modules(monkeypatch)
    state_db_path = tmp_path / "platform-state.sqlite3"
    settings = config_module.BackendSettings(
        app_env="test",
        state_db_path=str(state_db_path),
    )

    first_app = _create_test_app(app_module, settings)
    create_environment_route = _find_route(first_app, "/api/v1/environments", "POST")
    detail_environment_route = _find_route(
        first_app, "/api/v1/environments/{environment_id}", "GET"
    )
    create_run_route = _find_route(first_app, "/api/v1/runs", "POST")
    list_runs_route = _find_route(first_app, "/api/v1/runs", "GET")
    detail_run_route = _find_route(first_app, "/api/v1/runs/{run_id}", "GET")
    suites_route = _find_route(first_app, "/api/v1/suites", "GET")
    management_schema_module = importlib.import_module("pyta_platform_backend.schemas.management")

    created_environment = create_environment_route.endpoint(
        management_schema_module.CreateEnvironmentRequest(
            name="灰度环境",
            base_url="https://gray.example.com",
            auth_mode="Token + Header",
            status="online",
            variables={"tenant": "gray"},
        )
    )
    created_run = create_run_route.endpoint(
        run_schema_module.CreateRunRequest(
            suite_id="demo-login-auth",
            environment_id=created_environment.id,
            trigger_source="manual",
            requested_by="tester",
            payload=_valid_payload(origin="persistence-test"),
        )
    )

    assert list_runs_route.endpoint(limit=20, offset=0).total == 1
    assert detail_environment_route.endpoint(created_environment.id).variables == {"tenant": "gray"}
    assert suites_route.endpoint() == []

    second_app = _create_test_app(app_module, settings)
    detail_environment_route = _find_route(
        second_app, "/api/v1/environments/{environment_id}", "GET"
    )
    list_runs_route = _find_route(second_app, "/api/v1/runs", "GET")
    detail_run_route = _find_route(second_app, "/api/v1/runs/{run_id}", "GET")
    suites_route = _find_route(second_app, "/api/v1/suites", "GET")

    persisted_environment = detail_environment_route.endpoint(created_environment.id)
    assert persisted_environment.name == "灰度环境"
    assert persisted_environment.variables == {"tenant": "gray"}

    persisted_runs = list_runs_route.endpoint(limit=20, offset=0)
    assert persisted_runs.total == 1
    assert persisted_runs.items[0].run_id == created_run.run_id
    assert persisted_runs.items[0].environment_id == created_environment.id

    persisted_run_detail = detail_run_route.endpoint(created_run.run_id)
    assert persisted_run_detail.payload["origin"] == "persistence-test"
    assert persisted_run_detail.payload["environment"]["id"] == created_environment.id

    refreshed_suites = suites_route.endpoint()
    assert refreshed_suites == []


def test_sqlite_state_rehydrates_queued_tasks_after_app_recreation(monkeypatch, tmp_path):
    """重启后 queued 任务应重新进入 dispatcher，而不是只剩一条僵尸 run 记录。"""

    app_module, config_module, _ = _reload_backend_modules(monkeypatch)
    state_db_path = tmp_path / "platform-state.sqlite3"
    settings = config_module.BackendSettings(
        app_env="test",
        state_db_path=str(state_db_path),
    )

    first_app = _create_test_app(app_module, settings)

    run_schema = importlib.import_module("pyta_platform_backend.schemas.run")
    created = first_app.state.run_service.create_run(
        run_schema.CreateRunRequest(suite_id="restart", payload=_valid_payload())
    )

    second_app = _create_test_app(app_module, settings)
    run_by_id_route = _find_route(second_app, "/api/v1/worker/runs/{run_id}/execute", "POST")
    detail_route = _find_route(second_app, "/api/v1/runs/{run_id}", "GET")

    queued = run_by_id_route.endpoint(created.run_id)
    assert queued.status.value == "queued"
    executed = second_app.state.worker_runner.run_next()

    assert executed.run_id == created.run_id
    assert executed.status.value == "succeeded"

    detail = detail_route.endpoint(created.run_id)
    assert detail.status.value == "succeeded"
    assert "standard run executed" in (detail.status_message or "")


def test_worker_merges_environment_snapshot_into_execution_variables(monkeypatch):
    """worker 应把 environment 快照转成执行变量。"""

    _reload_backend_modules(monkeypatch)
    runner_module = importlib.import_module("pyta_platform_backend.workers.runner")
    dispatcher_module = importlib.import_module("pyta_platform_backend.workers.dispatcher")
    datetime_module = importlib.import_module("datetime")

    merged = runner_module.MemoryWorkerRunner._merge_environment_variables(
        dispatcher_module.DispatchTask(
            run_id="run-env-001",
            suite_id="suite-env",
            trigger_source="manual",
            requested_by="tester",
            payload={
                "environment": {
                    "id": "env-default-live",
                    "name": "默认联调环境",
                    "base_url": "https://api-test.yanjiai.com",
                    "auth_mode": "账号密码登录 + Token 注入",
                    "variables": {"tenant": "default"},
                }
            },
            dispatched_at=datetime_module.datetime.utcnow(),
        ),
        variables={"trace_id": "trace-001"},
    )

    assert merged["host"] == "https://api-test.yanjiai.com"
    assert merged["environment"]["id"] == "env-default-live"
    assert merged["trace_id"] == "trace-001"

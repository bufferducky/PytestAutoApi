"""R01 回归：真实 HTTP/ASGI 边界、事务竞争和故障注入，不只验证假路由。"""

import importlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest


def payload(cases=None, **overrides):
    return {
        "execution_mode": "standard_run",
        "transport_mode": "live",
        "run_definition": {"cases": cases if cases is not None else [case("check")]},
        **overrides,
    }


def case(name, url="https://example.test", **extra):
    return {
        "case_id": name,
        "title": name,
        "request": {"url": url},
        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
        **extra,
    }


@pytest.fixture
def backend(tmp_path, local_http):
    # 旧装配测试注入 fake 模块。本组重新导入真实 FastAPI，验证真正 ASGI 行为。
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    app_module = importlib.import_module("pyta_platform_backend.app")
    settings = importlib.import_module("pyta_platform_backend.config").BackendSettings(
        app_env="test",
        state_db_path=str(tmp_path / "state.sqlite3"),
    )
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    app = app_module.create_app(settings=settings)
    app.state.test_http_base = local_http
    return app, schema, settings


@pytest.fixture
def local_http():
    with http_service() as (base, *_):
        yield base


def create(app, schema, data):
    data = json.loads(json.dumps(data).replace("https://example.test", app.state.test_http_base))
    return app.state.run_service.create_run(schema.CreateRunRequest(suite_id="r01", payload=data))


def wait_for(client, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/runs/{run_id}").json()
        if data["status"] not in {"queued", "running"}:
            return data
        Event().wait(0.01)
    raise AssertionError("运行未在预算内得到终态")


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"execution_mode": "typo", "transport_mode": "live"},
        {"execution_mode": "standard_run"},
        {"execution_mode": "standard_run", "transport_mode": "typo"},
        payload(cases=[]),
        payload(timeout_seconds=0),
        payload(timeout_seconds=float("nan")),
        payload(cases=[case("same"), case("same")]),
    ],
)
def test_invalid_plan_never_persists_or_dispatches(backend, bad):
    app, schema, _ = backend
    with pytest.raises(Exception) as exc:
        create(app, schema, bad)
    assert exc.value.status_code == 400
    assert app.state.run_service.list_runs().total == 0
    assert not app.state.run_service.dispatcher.dispatched_tasks


@pytest.mark.parametrize(
    ("cases", "expected"),
    [
        ([case("skip", enabled=False)], "skipped"),
        ([case("setup", assertions=[])], "blocked"),
        ([case("dependent", depends_on=["missing"])], "blocked"),
        ([case("check")], "succeeded"),
    ],
)
def test_live_skip_no_assertion_and_missing_dependency_are_honest(backend, cases, expected):
    app, schema, _ = backend
    create(app, schema, payload(cases))
    result = app.state.worker_runner.run_next()
    assert result.status.value == expected
    assert result.validation_scope == "live"
    assert result.eligible_for_release == (expected == "succeeded")
    assert result.counts["planned"] == result.counts["total"] == len(cases)


def test_results_redacted_bounded_and_survive_recreation(backend, monkeypatch):
    app, schema, settings = backend
    secret = "unique-credential-sentinel"
    monkeypatch.setenv("PYTA_SECRET_EVIDENCE", secret)
    data = payload(
        [
            case(
                "check",
                request={
                    "url": "https://example.test/redaction",
                    "headers": {"Authorization": "Bearer {{credential}}"},
                    "body": {"password": "{{credential}}"},
                },
            )
        ],
    )
    data["run_definition"]["variables"] = {"credential": {"secret_ref": "env:PYTA_SECRET_EVIDENCE"}}
    run = create(app, schema, data)
    detail = app.state.worker_runner.run_next()
    assert detail.results, json.dumps(
        {"message": detail.status_message, "payload": detail.payload}, ensure_ascii=False
    )
    assert detail.results[0]["steps"][0]["response"] is not None, detail.results
    assert detail.results[0]["steps"][0]["response"]["truncated"]
    assert detail.results[0]["steps"][0]["assertions"][0]["actual"] == 200
    module = importlib.import_module("pyta_platform_backend.app")
    restarted = module.create_app(settings=settings)
    stored = restarted.state.run_service.get_run_detail(run.run_id)
    assert stored.results == detail.results
    dump = json.dumps(stored.model_dump(mode="json"))
    assert secret not in dump
    assert secret.encode() not in open(settings.state_db_path, "rb").read()
    repeated = restarted.state.run_service.rerun(run.run_id)
    assert repeated.run_id != run.run_id  # 合法凭证引用可以重放，秘密不落盘。


def test_only_one_sqlite_connection_can_claim_and_late_writes_conflict(backend):
    app, schema, settings = backend
    run = create(app, schema, payload())
    repo_module = importlib.import_module("pyta_platform_backend.repositories.run_repository")
    repos = [repo_module.SqlRunRepository(settings.state_db_path) for _ in range(2)]

    def claim(repo):
        try:
            return repo.claim(run.run_id)
        except repo_module.RunConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, repos))
    assert sum(item is not None for item in results) == 1
    winner = next(item for item in results if item)
    with pytest.raises(repo_module.RunConflict):
        repos[0].finish(run.run_id, "old-attempt", schema.RunStatus.SUCCEEDED, "late")
    done = repos[0].finish(run.run_id, winner.attempt_id, schema.RunStatus.ERROR, "injected")
    assert done.finished_at
    with pytest.raises(Exception) as exc:
        app.state.run_service.update_run_status(
            run.run_id,
            schema.UpdateRunStatusRequest(
                status="running",
                expected_version=done.version,
            ),
        )
    assert exc.value.status_code == 409
    with pytest.raises(Exception) as exc:
        app.state.run_service.update_run_status(
            run.run_id,
            schema.UpdateRunStatusRequest(
                status="succeeded",
                expected_version=done.version,
            ),
        )
    assert exc.value.status_code == 409


@contextmanager
def http_service():
    entered, release = Event(), Event()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append(self.path)
            if self.path == "/slow":
                entered.set()
                release.wait(5)
            if self.path == "/delay":
                Event().wait(0.2)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = {"code": 500 if self.path == "/cleanup-fail" else 200}
                if self.path.startswith("/redaction"):
                    body.update(
                        token="unique-credential-sentinel",
                        echo="unique-credential-sentinel",
                        large="x" * 70000,
                    )
                self.wfile.write(json.dumps(body).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls, entered, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_asgi_submission_is_nonblocking_cancel_still_cleans(backend):
    from fastapi.testclient import TestClient

    app, _, _ = backend
    with http_service() as (base, calls, entered, release), TestClient(app) as client:
        data = payload(
            [case("slow", base + "/slow"), case("later", base + "/later")], transport_mode="live"
        )
        data["run_definition"]["cleanup_cases"] = [case("cleanup", base + "/cleanup")]
        started = time.monotonic()
        response = client.post("/api/v1/runs", json={"suite_id": "slow", "payload": data})
        assert response.status_code == 202
        assert time.monotonic() - started < 1
        run_id = response.json()["run_id"]
        assert entered.wait(2)
        started = time.monotonic()
        assert client.get("/api/v1/health/live").status_code == 200
        assert client.post(f"/api/v1/worker/runs/{run_id}/execute").status_code == 202
        assert time.monotonic() - started < 1
        assert client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 200
        release.set()
        result = wait_for(client, run_id)
        assert result["status"] == "cancelled"
        assert calls == ["/slow", "/cleanup"]
        assert result["cleanup_status"] == "succeeded"
        assert result["cancel_requested_at"] and result["finished_at"]
        assert result["counts"]["blocked"] == 1
        assert not result["eligible_for_release"]


def test_real_http_timeout_stops_later_requests_and_cleans(backend):
    app, schema, _ = backend
    with http_service() as (base, calls, _, __):
        data = payload(
            [case("delay", base + "/delay"), case("later", base + "/later")],
            transport_mode="live",
            timeout_seconds=0.05,
        )
        data["run_definition"]["cleanup_cases"] = [case("cleanup", base + "/cleanup")]
        create(app, schema, data)
        result = app.state.worker_runner.run_next()
        assert result.status.value == "timed_out"
        assert "/later" not in calls and "/cleanup" in calls
        assert result.cleanup_status == "succeeded"


def test_evidence_write_failure_never_passes_and_still_cleans(backend, monkeypatch):
    app, schema, _ = backend
    with http_service() as (base, calls, _, __):
        data = payload(
            [case("first", base + "/first"), case("later", base + "/later")], transport_mode="live"
        )
        data["run_definition"]["cleanup_cases"] = [case("cleanup", base + "/cleanup")]
        create(app, schema, data)

        def fail(*args):
            raise OSError("disk unavailable")

        monkeypatch.setattr(app.state.run_service.repository, "append_result", fail)
        result = app.state.worker_runner.run_next()
        assert result.status.value == "error"
        assert "存储失败" in result.status_message
        assert calls == ["/first", "/cleanup"]
        assert result.cleanup_status == "succeeded"


def test_running_recovery_does_not_replay_write(backend):
    from fastapi.testclient import TestClient

    app, schema, settings = backend
    with http_service() as (base, calls, _, __):
        run = create(app, schema, payload([case("check", base + "/never")], transport_mode="live"))
        app.state.run_service.repository.claim(run.run_id)
        module = importlib.import_module("pyta_platform_backend.app")
        restarted = module.create_app(settings=settings)
        with TestClient(restarted) as client:
            detail = client.get(f"/api/v1/runs/{run.run_id}").json()
            assert detail["status"] == "interrupted"
            assert detail["cleanup_status"] == "needs_reconciliation"
            assert not calls


def test_queued_cancel_and_rerun_lineage(backend):
    app, schema, _ = backend
    run = create(app, schema, payload())
    cancelled = app.state.run_service.cancel_run(run.run_id)
    assert cancelled.status.value == "cancelled"
    assert app.state.worker_runner.run_next() is None
    again = app.state.run_service.rerun(run.run_id)
    result = app.state.worker_runner.run_next()
    assert again.run_id != run.run_id
    assert result.original_run_id == run.run_id
    assert result.status.value == "succeeded"


def test_cleanup_failure_keeps_assertion_result_but_blocks_release(backend):
    app, schema, _ = backend
    data = payload()
    data["run_definition"]["cleanup_cases"] = [case("cleanup", "https://example.test/cleanup-fail")]
    create(app, schema, data)
    result = app.state.worker_runner.run_next()
    assert result.status.value == "succeeded"
    assert result.cleanup_status == "cleanup_failed"
    assert not result.eligible_for_release
    assert result.results[-1]["phase"] == "cleanup"
    assert result.results[-1]["status"] == "failed"


def test_offline_store_transaction_failure_rolls_back_run_evidence(backend):
    app, schema, _ = backend
    created = create(app, schema, payload())
    repo = app.state.run_service.repository
    before = repo.get_detail(created.run_id)
    with pytest.raises(RuntimeError, match="transaction interrupted"):
        with repo._transaction():
            record = repo.get_by_id(created.run_id)
            record.status_message = "must roll back"
            repo._save(record)
            raise RuntimeError("transaction interrupted")
    after = repo.get_detail(created.run_id)
    assert after.status == before.status
    assert after.status_message == before.status_message


def test_same_database_rejects_second_worker_host(backend):
    app, _, settings = backend
    module = importlib.import_module("pyta_platform_backend.app")
    second = module.create_app(settings=settings)
    app.state.worker_host.start()
    try:
        with pytest.raises(RuntimeError, match="单实例"):
            second.state.worker_host.start()
    finally:
        app.state.worker_host.stop()


def test_lost_queue_hint_does_not_lose_persisted_task(backend):
    app, schema, _ = backend
    created = create(app, schema, payload())
    assert app.state.run_service.dispatcher.pull_next().run_id == created.run_id
    detail = app.state.worker_runner.run_next()
    assert detail.run_id == created.run_id
    assert detail.status.value == "succeeded"
    assert app.state.worker_runner.run_next() is None


def test_live_evidence_is_visible_before_terminal_and_release_is_scoped(backend):
    from fastapi.testclient import TestClient

    app, _, _ = backend
    with http_service() as (base, calls, entered, release), TestClient(app) as client:
        data = payload(
            [case("fast", base + "/fast"), case("slow", base + "/slow")], transport_mode="live"
        )
        created = client.post(
            "/api/v1/runs", json={"suite_id": "incremental", "payload": data}
        ).json()
        assert entered.wait(2)
        mid = client.get(f"/api/v1/runs/{created['run_id']}/results").json()
        assert mid["status"] == "running"
        assert len(mid["results"]) == 1
        assert mid["results"][0]["case_id"] == "fast"
        release.set()
        result = wait_for(client, created["run_id"])
        assert result["status"] == "succeeded"
        assert result["validation_scope"] == "live"
        assert result["eligible_for_release"]
        assert result["counts"]["executed"] == 2
        assert calls == ["/fast", "/slow"]
        exported = client.get(f"/api/v1/runs/{created['run_id']}/export").json()
        assert exported["transport_mode"] == "live"
        assert exported["results"] == result["results"]


def test_rerun_keeps_environment_snapshot_after_environment_edit(backend):
    app, schema, _ = backend
    environment_schema = importlib.import_module("pyta_platform_backend.schemas.management")
    environment = app.state.management_service.create_environment(
        environment_schema.CreateEnvironmentRequest(
            auth_mode="none", name="snapshot-env", base_url=app.state.test_http_base
        )
    )
    run = app.state.run_service.create_run(
        schema.CreateRunRequest(
            suite_id="snapshot",
            environment_id=environment.id,
            payload=payload(),
        )
    )
    original = app.state.run_service.get_run_detail(run.run_id)
    app.state.management_service._repository.update_environment(
        environment.id,
        name="changed",
        base_url="https://changed.test",
        auth_mode="changed",
        status="draft",
        variables={"changed": True},
    )
    app.state.run_service.cancel_run(run.run_id)
    repeated = app.state.run_service.rerun(run.run_id)
    again = app.state.run_service.get_run_detail(repeated.run_id)
    assert again.environment_id == original.environment_id
    assert again.environment_name == original.environment_name
    assert again.payload["environment"] == original.payload["environment"]


def test_queued_without_secrets_recovers_and_executes_in_real_lifespan(backend):
    from fastapi.testclient import TestClient

    app, schema, settings = backend
    created = create(app, schema, payload())
    module = importlib.import_module("pyta_platform_backend.app")
    restarted = module.create_app(settings=settings)
    with TestClient(restarted) as client:
        result = wait_for(client, created.run_id)
        assert result["status"] == "succeeded"
        assert result["counts"]["assertions"] == 1
        assert result["validation_scope"] == "live"
        assert result["eligible_for_release"]


@pytest.mark.parametrize("mode", ["standard_run", "legacy_yaml", "ui_journey"])
@pytest.mark.parametrize(
    "extra",
    [
        {"transport_mode": "mock"},
        {"mock_response": {}},
        {"mock_case_responses": {}},
        {"mock_latency": 0},
    ],
)
def test_all_new_execution_modes_reject_simulation_before_persisting(backend, mode, extra):
    app, schema, _ = backend
    data = payload(execution_mode=mode, **extra)
    with pytest.raises(Exception) as exc:
        app.state.run_service._create_prepared(
            schema.CreateRunRequest(suite_id="reject", payload=data), None
        )
    assert exc.value.status_code == 400
    assert app.state.run_service.list_runs().total == 0


@pytest.mark.parametrize("imported", [False, True])
def test_historical_queued_evidence_cannot_be_manually_started_or_rerun(backend, imported):
    app, schema, _ = backend
    repo = app.state.run_service.repository
    record = repo.create_pending_run(
        schema.CreateRunRequest(
            suite_id="historical", payload=payload(transport_mode="live" if imported else "mock")
        )
    )
    with repo._transaction():
        record = repo.get_by_id(record.run_id)
        if imported:
            record.execution["migration"] = {"do_not_resume": True}
        repo._save(record)
    dispatcher = importlib.import_module("pyta_platform_backend.workers.dispatcher")
    task = dispatcher.DispatchTask(
        run_id=record.run_id,
        suite_id=record.suite_id,
        trigger_source=record.trigger_source,
        requested_by=record.requested_by,
        payload=record.payload,
        dispatched_at=record.created_at,
    )
    assert app.state.worker_runner._consume_task(task) is None
    assert repo.get_detail(record.run_id).status.value == "queued"
    assert repo.get_detail(record.run_id).attempt_id is None
    for action in [app.state.worker_control_service.run_by_id, app.state.run_service.rerun]:
        with pytest.raises(Exception) as exc:
            action(record.run_id)
        assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "schema_name,values",
    [
        ("assets", {"transport_mode": "live", "mock_case_responses": {}}),
        (
            "schedules",
            {
                "name": "bad",
                "suite_id": "s",
                "suite_version": 1,
                "environment_id": "e",
                "transport_mode": "live",
                "cron": "* * * * *",
                "mock_case_responses": {},
            },
        ),
        ("run", {"suite_id": "s", "mock_response": {}}),
        ("journeys", {"mock_response": {}}),
    ],
)
def test_new_request_models_forbid_extra_simulation_fields(backend, schema_name, values):
    names = {
        "assets": "AssetRunRequest",
        "schedules": "ScheduleDefinition",
        "run": "CreateRunRequest",
        "journeys": "JourneyRunRequest",
    }
    module = importlib.import_module("pyta_platform_backend.schemas." + schema_name)
    with pytest.raises(ValueError):
        getattr(module, names[schema_name])(**values)


def test_dashboard_uses_live_aggregate_without_static_focus(backend, monkeypatch):
    app, _, _ = backend
    repo = app.state.run_service.repository
    monkeypatch.setattr(
        repo, "live_stats", lambda: {"total": 2001, "queued": 1002, "running": 2, "failed": 15}
    )
    overview = app.state.dashboard_service.get_overview()
    assert {metric.key: metric.value for metric in overview.metrics} == {
        "runs": "2001",
        "queued": "1002",
        "running": "2",
        "failed": "15",
    }
    assert overview.focus_items == []

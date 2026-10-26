"""R02：公开配置、密钥引用、独立会话、刷新与真实登录预检。"""

import hashlib
import importlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs

import pytest
from test_support import seed_test_environments


@pytest.fixture
def platform(tmp_path, monkeypatch):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    app_module = importlib.import_module("pyta_platform_backend.app")
    settings = importlib.import_module("pyta_platform_backend.config").BackendSettings(
        app_env="test",
        state_db_path=str(tmp_path / "context.sqlite3"),
    )
    monkeypatch.setenv("PYTA_SECRET_U", "user-sentinel")
    monkeypatch.setenv("PYTA_SECRET_P", "password-sentinel")
    return seed_test_environments(app_module.create_app(settings=settings)), settings


@contextmanager
def auth_server():
    requests, logins, counters = [], [], {}

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = (
                json.loads(raw)
                if "json" in self.headers.get("Content-Type", "")
                else {key: values[0] for key, values in parse_qs(raw.decode()).items()}
            )
            if self.path.startswith("/login"):
                logins.append((self.path, body, self.headers.get("Content-Type")))
                user = body.get("username", "")
                if self.path == "/login-bad":
                    self.send_json({"code": 500})
                elif self.path == "/login-missing":
                    self.send_json({"code": 200, "data": {}})
                else:
                    token = f"token-{user}-{len(logins)}"
                    self.send_json({"code": 200, "data": {"token": token, "expires": 120}})
                return
            self.business(body)

        def do_GET(self):
            self.business(None)

        def business(self, body):
            auth = self.headers.get("Authorization")
            project, tenant = self.headers.get("Dept-Id"), self.headers.get("Tenant-Id")
            requests.append((self.path, auth, project, tenant, body))
            counters[self.path] = counters.get(self.path, 0) + 1
            if (
                self.path == "/write"
                or self.path == "/always401"
                or self.path == "/refresh"
                and counters[self.path] == 1
            ):
                self.send_json({"code": 401}, 401)
            elif self.path == "/wrong-scope":
                self.send_json({"code": 200, "data": {"tenant": "other", "project": "other"}})
            elif self.path == "/info":
                self.send_json({"code": 200, "data": {"tenant": tenant, "project": project}})
            else:
                self.send_json({"code": 200})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests, logins
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def profiles(app, base, *, suffix="", bearer=False, form=False, login="/login"):
    service = app.state.context_service
    target = service.save(
        "targets",
        {
            "id": "target" + suffix,
            "name": "target" + suffix,
            "environment_id": "env-default-live",
            "base_url": base,
            "kind": "saas",
            "requires_context": True,
            "auth": {
                "mode": "password",
                "contract_confirmed": True,
                "login_path": login,
                "request_mode": "form" if form else "json",
                "password_transform": "md5",
                "header_template": "Bearer {token}" if bearer else "{token}",
                "expiry_path": "data.expires",
                "expiry_format": "relative_seconds",
            },
            "checks": [
                {
                    "name": "scope",
                    "path": "/info",
                    "query_contract_confirmed": True,
                    "tenant_path": "data.tenant",
                    "project_path": "data.project",
                }
            ],
        },
        creating=True,
    )
    identity = service.save(
        "identity-profiles",
        {
            "id": "identity" + suffix,
            "name": "tester",
            "target_ids": [target["id"]],
            "username_secret_ref": "env:PYTA_SECRET_U",
            "password_secret_ref": "env:PYTA_SECRET_P",
        },
        creating=True,
    )
    binding = service.save(
        "context-bindings",
        {
            "id": "binding" + suffix,
            "name": "project",
            "target_id": target["id"],
            "identity_id": identity["id"],
            "tenant_id": "tenant" + suffix,
            "project_id": "project" + suffix,
        },
        creating=True,
    )
    return target, identity, binding


def submit(app, target, identity, binding, paths=None, metadata=None):
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    definition = {
        "cases": [
            {
                "case_id": f"c{i}",
                "title": "query",
                "request": {"url": "{{host}}" + path},
                "metadata": metadata or {},
                "assertions": [{"name": "code", "selector": "code", "expected": 200}],
            }
            for i, path in enumerate(paths or ["/check"])
        ]
    }
    return app.state.run_service.create_run(
        schema.CreateRunRequest(
            suite_id="context",
            environment_id="env-default-live",
            target_id=target["id"],
            identity_id=identity["id"],
            context_binding_id=binding["id"],
            payload={
                "execution_mode": "standard_run",
                "transport_mode": "live",
                "run_definition": definition,
            },
        )
    )


@pytest.mark.parametrize(("bearer", "form"), [(False, False), (True, True)])
def test_real_auth_format_hash_context_and_no_persisted_secrets(platform, bearer, form):
    app, settings = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base, bearer=bearer, form=form)
        run = submit(app, target, identity, binding)
        result = app.state.worker_runner.run_next()
        assert result.status.value == "succeeded"
        assert logins[0][1] == {
            "username": "user-sentinel",
            "password": hashlib.md5(b"password-sentinel").hexdigest(),
        }
        expected = ("Bearer " if bearer else "") + "token-user-sentinel-1"
        assert requests[0][1:4] == (expected, "project", "tenant")
        detail = app.state.run_service.get_run_detail(run.run_id)
        content = json.dumps(detail.model_dump(mode="json"))
        for secret in [
            "user-sentinel",
            "password-sentinel",
            "token-user-sentinel-1",
            hashlib.md5(b"password-sentinel").hexdigest(),
        ]:
            assert secret not in content
            assert secret.encode() not in open(settings.state_db_path, "rb").read()
        assert detail.payload["context_snapshots"]["default"]["identity"][
            "password_secret_ref"
        ].startswith("env:")
        assert (
            not app.state.run_service.repository.get_by_id(run.run_id)
            .payload["run_definition"]["cases"][0]["request"]
            .get("headers")
        )


def test_explicit_safe_query_retries_once_preserves_initial_failure(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        submit(
            app,
            target,
            identity,
            binding,
            ["/refresh"],
            {"safe_to_replay": True, "operation_kind": "query"},
        )
        result = app.state.worker_runner.run_next()
        assert result.status.value == "succeeded"
        assert len(logins) == 2 and len(requests) == 2
        trace = result.results[0]["steps"][0]["attempts"]
        assert [event["status_code"] for event in trace if event["kind"] == "request"] == [401, 200]
        submit(
            app,
            target,
            identity,
            binding,
            ["/always401"],
            {"safe_to_replay": True, "operation_kind": "query"},
        )
        failed = app.state.worker_runner.run_next()
        assert failed.status.value == "failed"
        assert len([r for r in requests if r[0] == "/always401"]) == 2


def test_write_never_replays_even_with_safe_flag(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        submit(
            app,
            target,
            identity,
            binding,
            ["/write"],
            {"safe_to_replay": True, "operation_kind": "write"},
        )
        assert app.state.worker_runner.run_next().status.value == "failed"
        assert len(logins) == len(requests) == 1


def test_missing_ref_blocks_before_any_login(platform, monkeypatch):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        monkeypatch.delenv("PYTA_SECRET_P")
        submit(app, target, identity, binding)
        result = app.state.worker_runner.run_next()
        assert result.status.value == "error"
        assert "secret_ref" in result.status_message
        assert result.results[0]["status"] == "blocked"
        assert not requests and not logins


def test_parallel_runs_isolate_targets_identities_and_projects(platform, monkeypatch):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        a = profiles(app, base, suffix="a")
        b = profiles(app, base, suffix="b", bearer=True)
        monkeypatch.setenv("PYTA_SECRET_OTHER_USER", "other-sentinel")
        b_identity = {**b[1], "username_secret_ref": "env:PYTA_SECRET_OTHER_USER"}
        b_identity = app.state.context_service.save("identity-profiles", b_identity)
        first, second = submit(app, *a), submit(app, b[0], b_identity, b[2])
        with ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(app.state.worker_runner.run_by_id, [first.run_id, second.run_id])
            )
        assert all(result.status.value == "succeeded" for result in results)
        for _, auth, project, tenant, _ in requests:
            if project == "projecta":
                assert auth.startswith("token-user-sentinel-") and tenant == "tenanta"
            else:
                assert (
                    project == "projectb"
                    and auth.startswith("Bearer token-other-sentinel-")
                    and tenant == "tenantb"
                )


def test_config_crud_revision_preflight_snapshot_and_restart(platform):
    from fastapi.testclient import TestClient

    app, settings = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        request = importlib.import_module("pyta_platform_backend.schemas.context").PreflightRequest(
            target_id=target["id"],
            context_binding_id=binding["id"],
            execute_login=True,
        )
        result = app.state.context_service.preflight("env-default-live", request)
        assert all(value == "passed" for value in result.values())
        run = submit(app, target, identity, binding)
        updated = app.state.context_service.save("targets", {**target, "name": "updated"})
        with pytest.raises(Exception) as exc:
            app.state.context_service.save("targets", target)
        assert exc.value.status_code == 409
        with pytest.raises(Exception) as exc:
            app.state.context_service.delete("targets", target["id"], updated["revision"])
        assert exc.value.status_code == 409
        assert (
            app.state.run_service.get_run_detail(run.run_id).payload["context_snapshots"][
                "default"
            ]["target"]["name"]
            == "target"
        )
        module = importlib.import_module("pyta_platform_backend.app")
        restarted = module.create_app(settings=settings)
        with TestClient(restarted) as client:
            assert client.get("/api/v1/targets").status_code == 200
            assert (
                client.get("/api/v1/identity-profiles").json()[0]["password_secret_ref"]
                == "env:PYTA_SECRET_P"
            )
            status = client.post(
                "/api/v1/environments/env-default-live/preflight",
                json={
                    "target_id": target["id"],
                    "context_binding_id": binding["id"],
                    "execute_login": False,
                },
            ).json()
            assert status["configuration"] == "passed" and status["authentication"] == "not_run"
            assert client.patch("/api/v1/targets/target", json=target).status_code == 409


@pytest.mark.parametrize(
    ("login", "code"),
    [("/login-bad", "login_business_code_failed"), ("/login-missing", "login_token_missing")],
)
def test_preflight_authentication_failures_are_separate_from_network(platform, login, code):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base, login=login)
        model = importlib.import_module("pyta_platform_backend.schemas.context").PreflightRequest
        result = app.state.context_service.preflight(
            "env-default-live",
            model(
                target_id=target["id"],
                context_binding_id=binding["id"],
                execute_login=True,
            ),
        )
        assert result["authentication"] == "failed" and result["error_code"] == code
        assert not requests


def test_invalid_cross_environment_binding_and_secret_paths_rejected(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        with pytest.raises(ValueError):
            app.state.context_service.snapshot(target["id"], environment_id="env-demo-mock")
        with pytest.raises(ValueError):
            app.state.context_service.snapshot(target["id"])
        with pytest.raises(Exception) as exc:
            app.state.context_service.save(
                "identity-profiles",
                {**identity, "id": "bad", "password_secret_ref": "/etc/passwd"},
                creating=True,
            )
        assert exc.value.status_code == 400
        assert not requests and not logins


def test_expiry_refreshes_before_query_without_reusing_stale_token(platform):
    import time

    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        snapshot = app.state.context_service.snapshot(target["id"], binding_id=binding["id"])
        module = importlib.import_module("pyta_platform_backend.workers.context_transport")
        transport = module.ContextTransport({"default": snapshot})
        session = transport._session("default")
        session.login(None, None, [])
        session.expiry = time.time() - 10
        engine = importlib.import_module("testflow_engine")
        context = engine.ExecutionContext(run_id="expiry")
        step = engine.TestCaseDefinition(
            case_id="read", title="read", request=engine.RequestSpec(url=base + "/check")
        )
        try:
            transport.send(step.request, context, step)
            assert len(logins) == 2
            assert requests[0][1].endswith("-2")
        finally:
            transport.close()


def test_single_run_explicit_context_switch_does_not_leave_headers(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, first = profiles(app, base)
        second = app.state.context_service.save(
            "context-bindings",
            {
                **first,
                "id": "second",
                "name": "second",
                "project_id": "second-project",
            },
            creating=True,
        )
        schema = importlib.import_module("pyta_platform_backend.schemas.run")
        run = app.state.run_service.create_run(
            schema.CreateRunRequest(
                suite_id="switch",
                environment_id="env-default-live",
                target_id=target["id"],
                context_binding_id=first["id"],
                additional_context_binding_ids=[second["id"]],
                payload={
                    "execution_mode": "standard_run",
                    "transport_mode": "live",
                    "run_definition": {
                        "cases": [
                            {
                                "case_id": "a",
                                "title": "a",
                                "request": {"url": "{{host}}/a"},
                                "assertions": [
                                    {"name": "code", "selector": "code", "expected": 200}
                                ],
                            },
                            {
                                "case_id": "b",
                                "title": "b",
                                "metadata": {"context_binding_id": second["id"]},
                                "request": {"url": "{{host}}/b"},
                                "assertions": [
                                    {"name": "code", "selector": "code", "expected": 200}
                                ],
                            },
                        ]
                    },
                },
            )
        )
        result = app.state.worker_runner.run_next()
        assert result.status.value == "succeeded"
        assert [item[2] for item in requests] == ["project", "second-project"]
        assert requests[0][1] != requests[1][1]
        assert result.run_id == run.run_id


def test_environment_revision_secret_rejection_and_reference_guard(platform):
    from fastapi.testclient import TestClient

    app, _ = platform
    with TestClient(app) as client:
        detail = client.get("/api/v1/environments/env-default-live").json()
        assert detail["revision"]
        updated = client.patch(
            "/api/v1/environments/env-default-live",
            json={
                "name": "changed",
                "expected_revision": detail["revision"],
            },
        )
        assert updated.status_code == 200
        assert (
            client.patch(
                "/api/v1/environments/env-default-live",
                json={
                    "name": "stale",
                    "expected_revision": detail["revision"],
                },
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/v1/environments",
                json={
                    "name": "secret",
                    "base_url": "https://example.test",
                    "auth_mode": "test",
                    "variables": {"password": "should-not-be-stored"},
                },
            ).status_code
            == 400
        )
        assert client.delete("/api/v1/environments/env-default-live").status_code == 409


def test_preflight_rate_limit_and_network_category(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
    # 已关闭的本地服务，不碰公司接口。
    model = importlib.import_module("pyta_platform_backend.schemas.context").PreflightRequest
    request = model(target_id=target["id"], context_binding_id=binding["id"], execute_login=True)
    for _ in range(3):
        result = app.state.context_service.preflight("env-default-live", request)
        assert result["service"] == "failed"
    with pytest.raises(Exception) as exc:
        app.state.context_service.preflight("env-default-live", request)
    assert exc.value.status_code == 429


def test_snapshot_replay_resolves_rotated_secret_and_revocation_blocks(platform, monkeypatch):
    app, settings = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        original = submit(app, target, identity, binding)
        assert app.state.worker_runner.run_next().status.value == "succeeded"
        module = importlib.import_module("pyta_platform_backend.app")
        restarted = module.create_app(settings=settings)
        monkeypatch.setenv("PYTA_SECRET_P", "rotated-password-sentinel")
        replay = restarted.state.run_service.rerun(original.run_id)
        assert restarted.state.worker_runner.run_next().status.value == "succeeded"
        assert logins[-1][1]["password"] == hashlib.md5(b"rotated-password-sentinel").hexdigest()
        monkeypatch.delenv("PYTA_SECRET_P")
        restarted.state.run_service.rerun(replay.run_id)
        assert restarted.state.worker_runner.run_next().status.value == "error"
        assert len(logins) == 2


def test_inline_reference_compat_resolves_once_and_template_remains_public(platform):
    app, settings = platform
    with auth_server() as (base, requests, logins):
        schema = importlib.import_module("pyta_platform_backend.schemas.run")
        data = {
            "execution_mode": "standard_run",
            "transport_mode": "live",
            "run_definition": {
                "variables": {"creds": {"secret_ref": "env:PYTA_SECRET_P", "transform": "md5"}},
                "cases": [
                    {
                        "case_id": "send",
                        "title": "send",
                        "request": {
                            "method": "POST",
                            "url": base + "/check",
                            "body": {"password": "{{creds}}"},
                        },
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    }
                ],
            },
        }
        run = app.state.run_service.create_run(
            schema.CreateRunRequest(suite_id="inline-ref", payload=data)
        )
        result = app.state.worker_runner.run_next()
        assert result.status.value == "succeeded"
        assert requests[0][-1]["password"] == hashlib.md5(b"password-sentinel").hexdigest()
        assert (
            result.payload["run_definition"]["cases"][0]["request"]["body"]["password"]
            == "{{creds}}"
        )
        repeated = app.state.run_service.rerun(run.run_id)
        assert app.state.worker_runner.run_next().run_id == repeated.run_id


def test_context_cleanup_receives_its_own_budget_after_main_timeout(platform):
    import time

    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        module = importlib.import_module("pyta_platform_backend.workers.context_transport")
        engine_module = importlib.import_module("testflow_engine")
        snapshot = app.state.context_service.snapshot(target["id"], binding_id=binding["id"])
        transport = module.ContextTransport({"default": snapshot}, timeout_seconds=0.5)

        class Delay(engine_module.EnginePlugin):
            def after_case(self, case, result, context):
                if case.case_id == "main":
                    time.sleep(0.6)

        def make(name):
            return engine_module.TestCaseDefinition(
                case_id=name,
                title=name,
                request=engine_module.RequestSpec(url="{{host}}/" + name),
                assertions=[
                    engine_module.AssertionSpec(name="code", selector="code", expected=200)
                ],
            )

        flow = engine_module.TestFlowEngine(
            transport=transport, plugins=[module.ContextAuthPlugin(transport), Delay()]
        )
        try:
            result = flow.execute_run(
                engine_module.TestRunDefinition(
                    cases=[make("main")],
                    cleanup_cases=[make("cleanup")],
                    variables={"host": base},
                ),
                timeout_seconds=0.5,
                cleanup_timeout_seconds=1,
            )
            assert result.status.value == "timed_out"
            assert "/cleanup" in [r[0] for r in requests]
            assert result.cleanup_status == "succeeded"
        finally:
            transport.close()


def test_additional_context_missing_rejected_before_login(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        with pytest.raises(Exception) as exc:
            submit(app, target, identity, binding, metadata={"context_binding_id": "not-fixed"})
        assert exc.value.status_code == 400
        assert not logins and not requests


def test_legacy_sensitive_records_are_marked_and_exported_redacted(platform):
    import sqlite3

    from fastapi.testclient import TestClient

    app, settings = platform
    with sqlite3.connect(settings.state_db_path) as db:
        db.execute(
            """INSERT INTO runs (
            run_id,suite_id,trigger_source,requested_by,payload_json,status,created_at,updated_at,execution_json
        ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "legacy",
                "legacy",
                "manual",
                "tester",
                json.dumps({"password": "legacy-secret-sentinel"}),
                "succeeded",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                "{}",
            ),
        )
    with TestClient(app) as client:
        exported = client.get("/api/v1/runs/legacy/export")
        assert exported.json()["legacy_sensitive"] is True
        assert "legacy-secret-sentinel" not in exported.text
        assert exported.json()["payload"]["password"] == "[REDACTED]"


def test_profile_delete_keeps_revision_history_and_requires_detaching(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        with pytest.raises(Exception) as exc:
            app.state.context_service.delete(
                "identity-profiles", identity["id"], identity["revision"]
            )
        assert exc.value.status_code == 409
        app.state.context_service.delete("context-bindings", binding["id"], binding["revision"])
        app.state.context_service.delete("identity-profiles", identity["id"], identity["revision"])
        app.state.context_service.delete("targets", target["id"], target["revision"])
        with pytest.raises(Exception) as exc:
            app.state.context_service.get("targets", target["id"])
        assert exc.value.status_code == 404
        with pytest.raises(Exception) as exc:
            app.state.context_service.save("targets", target, creating=True)
        assert exc.value.status_code == 409
        assert app.state.context_service.repository.exists("targets", target["id"])


@pytest.mark.parametrize(
    ("fields", "path", "expected"),
    [
        ({}, "/info", "not_verified"),
        ({"tenant_path": "data.tenant"}, "/info", "not_verified"),
        ({"tenant_path": "data.tenant", "project_path": "data.project"}, "/wrong-scope", "failed"),
        ({"tenant_path": "data.tenant", "project_path": "data.project"}, "/info", "passed"),
    ],
)
def test_preflight_requires_both_scope_dimensions(platform, fields, path, expected):
    from fastapi.testclient import TestClient

    app, _ = platform
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        app.state.context_service.save(
            "targets",
            {
                **target,
                "checks": [
                    {"name": "scope", "path": path, "query_contract_confirmed": True, **fields}
                ],
            },
        )
        # 走公开预检路由，证明可达/登录成功不能被升级为项目归属通过。
        client = TestClient(app)
        result = client.post(
            "/api/v1/environments/env-default-live/preflight",
            json={
                "target_id": target["id"],
                "context_binding_id": binding["id"],
                "execute_login": True,
            },
        )
        assert result.status_code == 200
        assert result.json()["context"] == expected
        assert len(logins) == 1 and len(requests) == 1


def test_preflight_without_context_requirement_is_not_required(platform):
    app, _ = platform
    with auth_server() as (base, requests, logins):
        target = app.state.context_service.save(
            "targets",
            {
                "name": "public",
                "environment_id": "env-default-live",
                "base_url": base,
                "checks": [{"name": "health", "path": "/health", "query_contract_confirmed": True}],
            },
            creating=True,
        )
        model = importlib.import_module("pyta_platform_backend.schemas.context").PreflightRequest
        result = app.state.context_service.preflight(
            "env-default-live", model(target_id=target["id"], execute_login=True)
        )
        assert result["context"] == "not_required" and result["service"] == "passed"
        assert not logins


def test_public_terminal_headers_apply_to_login_and_context_queries(platform, monkeypatch):
    app, _ = platform
    transport_module = importlib.import_module("pyta_platform_backend.workers.context_transport")
    original = transport_module.HttpxTransport
    seen = []

    class CapturingTransport(original):
        def send(self, request, context, case):
            seen.append((request.url, dict(request.headers)))
            return super().send(request, context, case)

    monkeypatch.setattr(transport_module, "HttpxTransport", CapturingTransport)
    with auth_server() as (base, requests, logins):
        target, identity, binding = profiles(app, base)
        context = app.state.context_service
        context.save("targets", {**target, "request_headers": {"User-Agent": "test-mobile"}})
        model = importlib.import_module("pyta_platform_backend.schemas.context").PreflightRequest
        result = context.preflight(
            "env-default-live",
            model(target_id=target["id"], context_binding_id=binding["id"], execute_login=True),
        )
        assert result["context"] == "passed"
        assert len(seen) == 2
        assert all(headers["User-Agent"] == "test-mobile" for _, headers in seen)
        from fastapi import HTTPException

        current = context.get("targets", target["id"])
        with pytest.raises(HTTPException) as exc:
            context.save("targets", {**current, "request_headers": {"Dept-Id": "other"}})
        assert exc.value.status_code == 400

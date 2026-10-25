"""R06：错误分类、脱敏附件、对比、筛选及显式证据保留。"""

import base64
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import perf_counter

import pytest


@pytest.fixture
def app(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    module = importlib.import_module("pyta_platform_backend.app")
    app = module.create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "diagnostic.sqlite3")
        )
    )

    app.state.http_bodies = {}
    app.state.check_code = 200
    app.state.prepare_ids = ["first", "second"]
    app.state.object_codes = {"first": 200, "second": 500, "fresh-second": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/check":
                body = {"code": app.state.check_code}
            elif self.path == "/prepare":
                body = {"data": {"id": app.state.prepare_ids.pop(0)}}
            elif self.path.startswith("/objects/"):
                body = {"code": app.state.object_codes[self.path.rsplit("/", 1)[-1]]}
            else:
                body = app.state.http_bodies[self.path]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    app.state.test_http_base = f"http://127.0.0.1:{server.server_port}"
    schema = importlib.import_module("pyta_platform_backend.schemas.management")
    env = app.state.management_service.create_environment(
        schema.CreateEnvironmentRequest(
            auth_mode="none", name="diagnostics-local", base_url=app.state.test_http_base
        )
    )
    app.state.test_environment_id = env.id
    app.state.context_service.save(
        "targets",
        {
            "id": "diagnostics-local",
            "name": "local",
            "environment_id": env.id,
            "base_url": app.state.test_http_base,
        },
        creating=True,
    )
    try:
        yield app
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def create_run(app, *, success=False, body=None, mode="live"):
    path = "/run/" + str(len(app.state.http_bodies))
    app.state.http_bodies[path] = (
        body
        if body is not None
        else {"code": 200, "data": {"object": "correct" if success else "wrong"}}
    )
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    data = {
        "execution_mode": "standard_run",
        "transport_mode": mode,
        "run_definition": {
            "cases": [
                {
                    "case_id": "check",
                    "title": "object check",
                    "request": {"url": app.state.test_http_base + path},
                    "assertions": [
                        {"name": "object field", "selector": "data.object", "expected": "correct"}
                    ],
                }
            ]
        },
    }
    created = app.state.run_service.create_run(
        schema.CreateRunRequest(suite_id="diagnostic", payload=data)
    )
    app.state.worker_runner.run_next()
    return created.run_id


@pytest.mark.parametrize(
    "category",
    [
        "config",
        "authentication",
        "context",
        "data",
        "network",
        "executor",
        "external_service",
        "device",
    ],
)
def test_injected_errors_are_classified_without_inventing_cause(app, category):
    from testflow_engine import CallableTransport, EnginePlugin, RequestSpec, ResponseSnapshot
    from testflow_engine import TestCaseDefinition as Case
    from testflow_engine import TestFlowEngine as Engine
    from testflow_engine import TestRunDefinition as Run

    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    created = app.state.run_service.create_run(
        schema.CreateRunRequest(
            suite_id="inject",
            payload={
                "execution_mode": "standard_run",
                "transport_mode": "live",
                "run_definition": {
                    "cases": [
                        {
                            "case_id": "error",
                            "title": "error",
                            "request": {"url": "https://example.test"},
                        }
                    ]
                },
            },
        )
    )
    repo = app.state.run_service.repository
    claimed = repo.claim(created.run_id)

    class Fault(RuntimeError):
        pass

    class Plugin(EnginePlugin):
        def before_case(self, case, context):
            error = Fault("injected controlled fault")
            error.category = category
            raise error

    result = Engine(
        transport=CallableTransport(lambda *args: ResponseSnapshot(status_code=200)),
        plugins=[Plugin()],
    ).execute_run(
        Run(
            run_id=created.run_id,
            cases=[
                Case(
                    case_id="error", title="error", request=RequestSpec(url="https://example.test")
                )
            ],
        )
    )
    for case in result.cases:
        repo.append_result(
            created.run_id,
            claimed.attempt_id,
            case.model_dump(mode="json"),
            {"total": 1, "errors": 1},
        )
    repo.finish(
        created.run_id,
        claimed.attempt_id,
        schema.RunStatus.ERROR,
        "injected",
        cleanup_status="succeeded",
    )
    diagnostic = app.state.diagnostic_service.overview(created.run_id)
    assert diagnostic["first_failure"]["category"] == category
    assert diagnostic["first_failure"]["case_id"] == "error"
    assert diagnostic["first_failure"]["next_action"]


def test_wrong_object_missing_field_and_failure_summary_keep_expected_actual(app):
    run_id = create_run(app)
    result = app.state.diagnostic_service.overview(run_id)
    first = result["first_failure"]
    assert first["category"] == "assertion"
    assertion = result["timeline"][0]["steps"][0]["assertions"][0]
    assert assertion["expected"] == "correct" and assertion["actual"] == "wrong"
    missing = create_run(app, body={"code": 200, "data": {}})
    diagnostic = app.state.diagnostic_service.overview(missing)
    assert diagnostic["first_failure"]["category"] == "config"
    assert diagnostic["timeline"][0]["steps"][0]["assertions"][0]["actual_missing"]


def test_pii_credentials_and_text_query_are_redacted_before_storage_and_export(app):
    from fastapi.testclient import TestClient

    secret = "credential-private-sentinel"
    customer = "customer-private-sentinel"
    run_id = create_run(
        app,
        body={
            "code": 200,
            "token": secret,
            "customer_name": customer,
            "phone": "13900000123",
            "echo": secret,
            "data": {"object": "wrong"},
        },
    )
    with TestClient(app) as client:
        result = client.get(f"/api/v1/runs/{run_id}/diagnostic-export")
        assert result.status_code == 200
        for value in [secret, customer, "13900000123"]:
            assert value not in result.text
        artifact = client.post(
            f"/api/v1/runs/{run_id}/artifacts",
            json={
                "content_type": "application/json",
                "step_id": "check",
                "content": {
                    "token": secret,
                    "customer": {"name": customer},
                    "phone": 13900000123,
                    "signed_url": "https://storage.test/audio?signature=private-signature",
                },
            },
        ).json()
        content = client.get(f"/api/v1/artifacts/{artifact['artifact_id']}/content?run_id={run_id}")
        for value in [secret, customer, "13900000123", "private-signature"]:
            assert value not in content.text
        path = app.state.diagnostic_service.artifacts.root / artifact["artifact_id"]
        assert (
            secret.encode() not in path.read_bytes() and customer.encode() not in path.read_bytes()
        )
        raw = app.state.run_service.repository._connection.execute(
            "SELECT payload_json,execution_json FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        assert all(secret not in text and customer not in text for text in raw)


def test_artifact_integrity_scope_missing_and_unverified_media(app):
    service = app.state.diagnostic_service
    first = create_run(app)
    second = create_run(app)
    artifact = service.add_artifact(
        first,
        {"content_type": "application/json", "content": {"summary": "safe"}, "step_id": "check"},
    )
    with pytest.raises(Exception) as exc:
        service.artifact(artifact["artifact_id"], second, download=True)
    assert exc.value.status_code == 404
    path = service.artifacts.root / artifact["artifact_id"]
    path.write_bytes(b"tampered")
    with pytest.raises(Exception) as exc:
        service.artifact(artifact["artifact_id"], first, download=True)
    assert (
        exc.value.status_code == 409
        and service.artifact(artifact["artifact_id"])["availability"] == "corrupt"
    )
    with pytest.raises(Exception) as exc:
        service.artifact("../../etc/passwd")
    assert exc.value.status_code == 404
    with pytest.raises(Exception) as exc:
        service.add_artifact(
            first, {"content_type": "image/png", "base64": base64.b64encode(b"image").decode()}
        )
    assert exc.value.status_code == 400
    media = service.add_artifact(
        first,
        {
            "content_type": "audio/wav",
            "base64": base64.b64encode(b"synthetic-audio").decode(),
            "synthetic_test_data": True,
            "redaction_verified": True,
        },
    )
    (service.artifacts.root / media["artifact_id"]).unlink()
    with pytest.raises(Exception) as exc:
        service.artifact(media["artifact_id"], download=True)
    assert exc.value.status_code == 409


def test_lineage_comparison_and_filters_keep_original_failure(app):
    run_id = create_run(app)
    again = app.state.run_service.rerun(run_id)
    # 替身响应只为新run调整；旧run结果不能被新的成功覆盖。
    app.state.http_bodies["/run/0"]["data"]["object"] = "correct"
    app.state.worker_runner.run_next()
    compared = app.state.diagnostic_service.compare(run_id, again.run_id)
    assert compared["before"]["status"] == "failed" and compared["after"]["status"] == "succeeded"
    assert compared["after"]["original_run_id"] == run_id
    assert compared["lineage"]["first_failure_preserved"]
    selected = app.state.diagnostic_service.filtered_runs(status="failed", transport_mode="live")
    assert selected.total == 1 and selected.items[0].run_id == run_id
    assert app.state.diagnostic_service.filtered_runs(category="assertion").total == 1
    assert app.state.diagnostic_service.filtered_runs(transport_mode="mock").total == 0


def test_expiry_pin_dry_run_and_metadata_tombstone(app):
    service = app.state.diagnostic_service
    run_id = create_run(app)
    expired = service.add_artifact(run_id, {"content": {"summary": "safe"}})
    pinned = service.add_artifact(run_id, {"content": {"summary": "keep"}})
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    for meta in [expired, pinned]:
        service.artifacts.update({**meta, "expires_at": old})
    service.pin(pinned["artifact_id"], True)
    with pytest.raises(Exception) as exc:
        service.artifact(expired["artifact_id"], download=True)
    assert exc.value.status_code == 410
    preview = service.retention_preview()
    assert (
        preview["ready"] == [expired["artifact_id"]]
        and pinned["artifact_id"] in preview["preserved"]
    )
    assert service.artifacts.content(service.artifacts.get_artifact(expired["artifact_id"]))
    service.retention_apply(preview["ready"])
    assert service.artifact(expired["artifact_id"])["availability"] == "expired"
    service.pin(pinned["artifact_id"], False)
    plan = service.retention_preview()
    service.retention_apply(plan["ready"])
    repo = app.state.run_service.repository
    with repo._transaction():
        record = repo.get_by_id(run_id)
        record.finished_at = datetime.fromisoformat(old)
        repo._save(record)
    preview = service.retention_preview()
    assert run_id in preview["metadata_ready"]
    service.retention_apply([], preview["metadata_ready"])
    diagnostic = service.overview(run_id)
    assert diagnostic["evidence_completeness"] == "expired"
    assert diagnostic["first_failure"]["message"] and diagnostic["status"] == "failed"
    assert app.state.run_service.get_run_detail(run_id).evidence_pruned_at


def test_five_representative_failures_record_timing_with_explicit_automated_scope(app):
    service = app.state.diagnostic_service
    samples = []
    for body in [
        {"data": {"object": "wrong"}},
        {"data": {}},
        {"data": {"object": None}},
        {"data": {"object": []}},
        {"data": {"object": ""}},
    ]:
        run_id = create_run(app, body=body)
        opened = datetime.now(timezone.utc).isoformat()
        started = perf_counter()
        diagnostic = service.overview(run_id)
        summary = json.dumps(diagnostic)
        elapsed = perf_counter() - started
        recorded = service.timing(
            run_id,
            {
                "opened_at": opened,
                "summary_at": datetime.now(timezone.utc).isoformat(),
                "scope": "automated_local_query_to_summary_not_human_triage",
            },
        )
        assert diagnostic["first_failure"] and recorded["seconds"] >= 0 and summary
        samples.append(elapsed)
    assert len(samples) == 5


def test_true_asgi_diagnostics_and_retention_policy(app):
    from fastapi.testclient import TestClient

    run_id = create_run(app)
    with TestClient(app) as client:
        result = client.get(f"/api/v1/runs/{run_id}/diagnostics").json()
        assert result["first_failure"]["category"] == "assertion"
        assert client.get(f"/api/v1/runs/{run_id}/steps").json()[0]["case_id"] == "check"
        assert client.get("/api/v1/runs?status=failed&transport_mode=live").json()["total"] == 1
        policy = client.get("/api/v1/artifact-retention/policy").json()
        assert policy["metadata_days"] == 90
        assert (
            client.patch(
                "/api/v1/artifact-retention/policy", json={**policy, "attachment_days": 7}
            ).status_code
            == 200
        )
        assert (
            client.patch("/api/v1/artifact-retention/policy", json={"metadata_days": 0}).status_code
            == 400
        )
        assert client.get("/api/v1/run-trends").status_code == 400


def test_trends_require_same_dimensions_and_small_samples_have_no_percentage(app):
    service = app.state.asset_service
    scene = service.create(
        "scenarios",
        {
            "name": "trend",
            "target_ref": "diagnostics-local",
            "steps": [
                {
                    "contract_confirmed": True,
                    "step_id": "check",
                    "name": "check",
                    "request": {"url": "{{host}}/check"},
                    "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                }
            ],
        },
    )
    model = importlib.import_module("pyta_platform_backend.schemas.assets")
    service.publish(
        "scenarios", scene["id"], model.PublishRequest(expected_revision=1, change_note="trend")
    )
    for index in range(21):
        app.state.check_code = 500 if index == 0 else 200
        service.run(
            "scenarios",
            scene["id"],
            1,
            model.AssetRunRequest(
                transport_mode="live",
                environment_id=app.state.test_environment_id,
            ),
        )
        app.state.worker_runner.run_next()
        if index == 0:
            small = app.state.diagnostic_service.trends(
                app.state.test_environment_id, "live", scene["id"], 1
            )
            assert small["insufficient_samples"] and small["first_failure_rate"] is None
    trend = app.state.diagnostic_service.trends(
        app.state.test_environment_id, "live", scene["id"], 1
    )
    assert (
        trend["sample_size"] == 21
        and trend["first_failures"] == 1
        and trend["first_failure_rate"] == pytest.approx(1 / 21)
    )
    assert trend["duration_p95_seconds"] is not None
    live = app.state.diagnostic_service.trends(
        app.state.test_environment_id, "mock", scene["id"], 1
    )
    assert live["sample_size"] == 0 and live["first_failure_rate"] is None


def test_first_page_for_1000_local_records_and_active_evidence_not_collected(app):

    service = app.state.diagnostic_service
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    request = schema.CreateRunRequest(
        suite_id="list-benchmark",
        payload={
            "execution_mode": "standard_run",
            "transport_mode": "live",
            "run_definition": {
                "cases": [
                    {
                        "case_id": "check",
                        "title": "check",
                        "request": {"url": "https://example.test"},
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    }
                ]
            },
        },
    )
    # 仅临时库批量种1000条queued记录，不启动真实业务、也不声称是1000条通过用例。
    for _ in range(1000):
        app.state.run_service.repository.create_pending_run(request)
    started = perf_counter()
    first = service.filtered_runs(limit=20, transport_mode="live")
    elapsed = perf_counter() - started
    assert first.total == 1000 and len(first.items) == 20 and elapsed < 2
    queued = first.items[0].run_id
    artifact = service.add_artifact(queued, {"content": {"summary": "active"}})
    service.artifacts.update(
        {**artifact, "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    )
    assert artifact["artifact_id"] in service.retention_preview()["preserved"]


def test_failed_only_replay_rebuilds_selected_scope_and_is_not_full_suite_release(app):
    service = app.state.asset_service
    model = importlib.import_module("pyta_platform_backend.schemas.assets")
    refs = []
    for name in ["first", "second"]:
        scene = service.create(
            "scenarios",
            {
                "name": name,
                "target_ref": "diagnostics-local",
                "steps": [
                    {
                        "contract_confirmed": True,
                        "step_id": "prepare",
                        "name": "prepare",
                        "phase": "setup",
                        "request": {"url": "{{host}}/prepare"},
                        "extractors": [
                            {"name": "id", "selector": "data.id", "target": "outputs.prepare.id"}
                        ],
                    },
                    {
                        "contract_confirmed": True,
                        "step_id": "verify",
                        "name": "verify",
                        "phase": "verify",
                        "depends_on": ["prepare"],
                        "request": {"url": "{{host}}/objects/{{outputs.prepare.id}}"},
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    },
                ],
            },
        )
        service.publish(
            "scenarios", scene["id"], model.PublishRequest(expected_revision=1, change_note=name)
        )
        refs.append({"scenario_id": scene["id"], "version": 1})
    suite = service.create("suites", {"name": "suite", "scenarios": refs})
    service.publish(
        "suites", suite["id"], model.PublishRequest(expected_revision=1, change_note="suite")
    )
    original = service.run(
        "suites",
        suite["id"],
        1,
        model.AssetRunRequest(
            transport_mode="live",
            environment_id=app.state.test_environment_id,
        ),
    )
    assert app.state.worker_runner.run_next().status.value == "failed"
    repeated = app.state.run_service.rerun(original.run_id, failed_only=True)
    task = app.state.run_service.dispatcher.dispatched_tasks[-1]
    assert [case["case_id"] for case in task.payload["run_definition"]["cases"]] == [
        "s1__prepare",
        "s1__verify",
    ]
    app.state.prepare_ids = ["fresh-second"]
    result = app.state.worker_runner.run_next()
    assert result.run_id == repeated.run_id and result.status.value == "succeeded"
    assert result.validation_scope == "live_partial" and not result.eligible_for_release
    assert result.results[1]["steps"][0]["request"]["url"].endswith("/fresh-second")
    assert result.payload["scenario_refs"] == [
        {
            "id": refs[1]["scenario_id"],
            "version": 1,
            "hash": service.version("scenarios", refs[1]["scenario_id"], 1)["hash"],
        }
    ]
    # 父套件失败不能把已通过的第一个场景误算为失败。
    first_trend = app.state.diagnostic_service.trends(
        app.state.test_environment_id, "live", refs[0]["scenario_id"], 1
    )
    assert first_trend["first_failures"] == 0


def test_imported_history_preserved_and_excluded_from_live_statistics(app):
    service = app.state.diagnostic_service
    run_id = create_run(app, success=True)
    artifact = service.add_artifact(run_id, {"content": {"summary": "historical evidence"}})
    old = datetime.now(timezone.utc) - timedelta(days=100)
    service.artifacts.update({**artifact, "expires_at": old.isoformat()})
    repo = app.state.run_service.repository
    with repo._transaction():
        record = repo.get_by_id(run_id)
        record.finished_at = old
        record.execution["migration"] = {"source": "historical_demo", "do_not_resume": True}
        repo._save(record)
    assert repo.get_detail(run_id).validation_scope == "historical_demo"
    assert not repo.get_detail(run_id).eligible_for_release
    preview = service.retention_preview()
    assert artifact["artifact_id"] in preview["preserved"]
    assert artifact["artifact_id"] not in preview["ready"]
    assert run_id not in preview["metadata_ready"]
    assert service.filtered_runs(transport_mode="live").total == 0
    assert service.filtered_runs().total == 1
    _, content = service.artifact(artifact["artifact_id"], download=True)
    assert b"historical evidence" in content
    with pytest.raises(ValueError, match="受保护"):
        service.artifacts.expire(artifact)
    with pytest.raises(Exception, match="受保护"):
        repo.prune_evidence(run_id)

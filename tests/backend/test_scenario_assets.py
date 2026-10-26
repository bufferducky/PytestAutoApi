"""R03：真正的资产编辑/发布/编译/执行及只读研究导入。"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest


@pytest.fixture
def platform(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    module = importlib.import_module("pyta_platform_backend.app")
    settings = importlib.import_module("pyta_platform_backend.config").BackendSettings(
        app_env="test", state_db_path=str(tmp_path / "assets.sqlite3")
    )
    app = module.create_app(settings=settings)
    counter = [0]
    app.state.omit_first_output = False

    class Handler(BaseHTTPRequestHandler):
        def answer(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            index = counter[0]
            counter[0] += 1
            data = {} if index == 0 and app.state.omit_first_output else {"id": f"s{index}-id"}
            self.answer({"code": 200, "data": data})

        def do_GET(self):
            self.answer({"code": 200, "data": {"message": "hello"}})

        def do_DELETE(self):
            self.answer({"code": 200})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment_schema = importlib.import_module("pyta_platform_backend.schemas.management")
    env = app.state.management_service.create_environment(
        environment_schema.CreateEnvironmentRequest(
            auth_mode="none", name="asset-test", base_url=f"http://127.0.0.1:{server.server_port}"
        )
    )
    app.state.test_environment_id = env.id
    app.state.context_service.save(
        "targets",
        {
            "id": "asset-test",
            "name": "local",
            "environment_id": env.id,
            "base_url": f"http://127.0.0.1:{server.server_port}",
        },
        creating=True,
    )
    try:
        yield app, settings
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def draft(name="flow"):
    return {
        "name": name,
        "target_ref": "asset-test",
        "parameters_schema": {"message": {"type": "string", "required": True}},
        "parameters": {"message": "hello"},
        "steps": [
            {
                "step_id": "create",
                "name": "create",
                "contract_confirmed": True,
                "phase": "action",
                "operation_kind": "write",
                "request": {
                    "method": "POST",
                    "url": "{{host}}/objects",
                    "body": {"message": "{{params.message}}"},
                },
                "extractors": [
                    {"name": "object", "selector": "data.id", "target": "outputs.create.id"}
                ],
            },
            {
                "step_id": "verify",
                "name": "verify",
                "contract_confirmed": True,
                "phase": "verify",
                "depends_on": ["create"],
                "request": {"url": "{{host}}/objects/{{outputs.create.id}}"},
                "assertions": [
                    {"name": "message", "selector": "data.message", "expected": "hello"}
                ],
            },
            {
                "step_id": "cleanup",
                "name": "cleanup",
                "contract_confirmed": True,
                "phase": "cleanup",
                "depends_on": ["create"],
                "operation_kind": "write",
                "request": {"method": "DELETE", "url": "{{host}}/objects/{{outputs.create.id}}"},
                "assertions": [{"name": "code", "selector": "code", "expected": 200}],
            },
        ],
    }


def publish(app, scenario):
    model = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest
    return app.state.asset_service.publish(
        "scenarios",
        scenario["id"],
        model(expected_revision=scenario["revision"], change_note="test publish"),
    )


def request(mode="live", **extra):
    model = importlib.import_module("pyta_platform_backend.schemas.assets").AssetRunRequest
    return model(transport_mode=mode, **extra)


def test_asset_publish_execute_export_and_roundtrip_without_demo_edits(platform):
    app, settings = platform
    service = app.state.asset_service
    created = service.create("scenarios", draft())
    check = service.preview("scenarios", created["id"])
    assert check["valid"], check
    published = publish(app, created)
    run = service.run("scenarios", created["id"], 1, request())
    result = app.state.worker_runner.run_next()
    assert result.run_id == run.run_id and result.status.value == "succeeded", result.results
    assert result.cleanup_status == "succeeded"
    assert [item["case_id"] for item in result.results] == [
        "s0__create",
        "s0__verify",
        "s0__cleanup",
    ]
    assert result.results[1]["steps"][0]["request"]["url"].endswith("/objects/s0-id")
    exported = service.export("scenarios", created["id"], 1)
    imported = service.import_standard(exported)
    assert imported["draft"] == exported["data"]
    assert imported["id"] != created["id"]
    assert service.export("scenarios", created["id"], 1)["hash"] == published["hash"]
    restarted = importlib.import_module("pyta_platform_backend.app").create_app(settings=settings)
    assert restarted.state.asset_service.get("scenarios", created["id"]) == created


@pytest.mark.parametrize(
    ("mutate", "field"),
    [
        (lambda d: d["steps"].append({**d["steps"][-1]}), "step_id"),
        (lambda d: d["steps"][0].update(type="unknown"), "type"),
        (lambda d: d["steps"][0].update(depends_on=["verify"]), "depends_on"),
        (lambda d: d["steps"][0].update(extractors=[]), "reads"),
        (lambda d: d["steps"][1].update(plugin_refs=["arbitrary@99"]), "plugin_refs"),
        (lambda d: d["steps"][1]["request"].update(url="{{outputs.future.id}}"), "reads"),
    ],
)
def test_publish_preflight_reports_exact_step_errors(platform, mutate, field):
    app, _ = platform
    data = draft()
    mutate(data)
    created = app.state.asset_service.create("scenarios", data)
    check = app.state.asset_service.preview("scenarios", created["id"])
    assert not check["valid"]
    assert any(
        error["path"].startswith("steps.") and error["path"].endswith(field)
        for error in check["errors"]
    )
    with pytest.raises(Exception) as exc:
        publish(app, created)
    assert exc.value.status_code == 400
    assert app.state.run_service.list_runs().total == 0


def test_draft_revision_immutable_versions_and_suite_pins(platform):
    app, _ = platform
    service = app.state.asset_service
    first = service.create("scenarios", draft("first"))
    p1 = publish(app, first)
    second = service.create("scenarios", draft("second"))
    publish(app, second)
    suite = service.create(
        "suites",
        {
            "name": "core",
            "tags": ["core"],
            "scenarios": [
                {"scenario_id": first["id"], "version": 1},
                {"scenario_id": second["id"], "version": 1},
            ],
        },
    )
    model = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest
    service.publish("suites", suite["id"], model(expected_revision=1, change_note="pin both"))
    updated = service.update("scenarios", first["id"], 1, {**first["draft"], "name": "changed"})
    publish(app, updated)
    with pytest.raises(Exception) as exc:
        service.update("scenarios", first["id"], 1, first["draft"])
    assert exc.value.status_code == 409
    plan = service.plan("suites", suite["id"], 1, request())
    assert plan["scenario_refs"][0]["hash"] == p1["hash"]
    assert plan["scenario_refs"][0]["version"] == 1
    run = service.run("suites", suite["id"], 1, request())
    result = app.state.worker_runner.run_next()
    assert result.status.value == "succeeded", result.results
    reads = [
        r["steps"][0]["request"]["url"] for r in result.results if r["case_id"].endswith("__verify")
    ]
    assert reads[0].endswith("/s0-id") and reads[1].endswith("/s1-id")
    cleanups = [r["case_id"] for r in result.results if r["phase"] == "cleanup"]
    assert cleanups == ["s1__cleanup", "s0__cleanup"]
    assert service.get("scenarios", first["id"])["revision"] == 2
    assert run.run_id == result.run_id


def test_runtime_missing_output_blocks_dependency_not_other_scope(platform):
    app, _ = platform
    service = app.state.asset_service
    a = service.create("scenarios", draft())
    publish(app, a)
    b = service.create("scenarios", draft())
    publish(app, b)
    suite = service.create(
        "suites",
        {
            "name": "isolation",
            "scenarios": [
                {"scenario_id": a["id"], "version": 1},
                {"scenario_id": b["id"], "version": 1},
            ],
        },
    )
    model = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest
    service.publish("suites", suite["id"], model(expected_revision=1, change_note="test"))
    app.state.omit_first_output = True
    service.run("suites", suite["id"], 1, request())
    result = app.state.worker_runner.run_next()
    items = {item["case_id"]: item for item in result.results}
    assert items["s0__verify"]["status"] == "blocked"
    assert items["s1__verify"]["status"] == "passed"
    assert items["s0__create"]["steps"][0]["request_sent"]
    assert result.status.value == "error"


def test_live_requires_confirmed_contract_and_parameters_cannot_override_target(platform):
    app, _ = platform
    service = app.state.asset_service
    data = draft()
    data["steps"][0]["contract_confirmed"] = False
    created = service.create("scenarios", data)
    publish(app, created)
    with pytest.raises(Exception) as exc:
        service.plan("scenarios", created["id"], 1, request("live"))
    assert exc.value.status_code == 400
    with pytest.raises(Exception) as exc:
        service.plan(
            "scenarios", created["id"], 1, request(parameters={"host": "https://wrong.test"})
        )
    assert exc.value.status_code == 400


def test_research_import_is_idempotent_three_systems_and_not_live_coverage(platform):
    app, _ = platform
    service = app.state.asset_service
    result = service.import_research()
    assert result["sources"]["center"]["observations"] == 213
    assert result["sources"]["saas"]["observations"] == 346
    assert result["sources"]["app"]["observations"] == 91
    assert all(value["new"] == 0 for value in service.import_research()["sources"].values())
    summary = service.coverage_summary()
    assert summary["confirmed_risks"] == summary["verified_risks"] == 0
    assert {item["system"] for item in summary["items"]} == {"center", "saas", "app"}
    assert all(
        item["source"] and item["location"] and item["contract_status"] == "unconfirmed"
        for item in summary["items"]
    )
    assert not app.state.run_service.dispatcher.dispatched_tasks


def test_live_coverage_stales(platform):
    app, _ = platform
    service = app.state.asset_service
    created = service.create("scenarios", draft())
    publish(app, created)
    service.repository.save_coverage(
        {
            "id": "risk",
            "system": "saas",
            "module": "test",
            "risk": "risk",
            "contract_status": "confirmed",
            "contract_note": "test-contract / tester / 2026-10-25",
            "scenario_refs": [{"scenario_id": created["id"], "version": 1}],
        }
    )
    run = service.run("scenarios", created["id"], 1, request())
    app.state.worker_runner.run_next()
    repo = app.state.run_service.repository
    assert service.coverage_summary()["verified_risks"] == 1
    with repo._transaction():
        record = repo.get_by_id(run.run_id)
        record.finished_at = datetime.now(timezone.utc) - timedelta(days=8)
        repo._save(record)
    assert service.coverage_summary()["items"][0]["coverage_status"] == "stale"


def test_legacy_demo_import_is_draft_only_and_reports_unmapped_capability(platform, tmp_path):
    app, _ = platform
    service = app.state.asset_service
    with pytest.raises(Exception) as exc:
        service.import_demo("demo-persona-library", "asset-test")
    assert exc.value.status_code == 410
    legacy = service.import_legacy("data/Login/login.yaml", "asset-test")
    assert legacy["report"]["mapping"]["assert"] == "steps.assertions"
    assert legacy["asset"]["draft"]["source"]["sha256"]
    assert not app.state.run_service.dispatcher.dispatched_tasks
    with pytest.raises(Exception) as exc:
        service.import_legacy("/etc/passwd", "asset-test")
    assert exc.value.status_code == 400


def test_actual_asgi_editor_publish_plan_and_archive(platform):
    from fastapi.testclient import TestClient

    app, _ = platform
    with TestClient(app) as client:
        created = client.post("/api/v1/scenarios", json=draft()).json()
        identifier = created["id"]
        assert any(item["id"] == identifier for item in client.get("/api/v1/scenarios").json())
        assert client.post(f"/api/v1/scenarios/{identifier}/preflight").json()["valid"]
        published = client.post(
            f"/api/v1/scenarios/{identifier}/publish",
            json={"expected_revision": 1, "change_note": "UI publish"},
        ).json()
        plan = client.post(
            f"/api/v1/scenarios/{identifier}/versions/1/plan", json={"transport_mode": "live"}
        ).json()
        assert published["version"] == 1 and plan["side_effects"][0]["kind"] == "write"
        assert client.post(f"/api/v1/scenarios/{identifier}/copy").status_code == 201
        assert client.post(f"/api/v1/scenarios/{identifier}/archive?revision=1").status_code == 200
        assert (
            client.get(f"/api/v1/scenarios/{identifier}/versions/1/export").json()["hash"]
            == published["hash"]
        )


def test_compiled_lifecycle_with_actual_local_http(platform):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    app, _ = platform
    objects, calls = {}, []

    class Handler(BaseHTTPRequestHandler):
        def answer(self, data):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            objects["test-object"] = data
            calls.append("create")
            self.answer({"code": 200, "data": {"id": "test-object"}})

        def do_GET(self):
            calls.append("verify")
            self.answer({"code": 200, "data": objects[self.path.split("/")[-1]]})

        def do_DELETE(self):
            calls.append("cleanup")
            del objects[self.path.split("/")[-1]]
            self.answer({"code": 200})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = app.state.context_service.save(
            "targets",
            {
                "id": "lifecycle",
                "name": "local",
                "environment_id": app.state.test_environment_id,
                "base_url": f"http://127.0.0.1:{server.server_port}",
            },
            creating=True,
        )
        data = draft()
        data["target_ref"] = target["id"]
        for step in data["steps"]:
            step["contract_confirmed"] = True
        created = app.state.asset_service.create("scenarios", data)
        publish(app, created)
        app.state.asset_service.run("scenarios", created["id"], 1, request("live"))
        result = app.state.worker_runner.run_next()
        assert result.status.value == "succeeded", result.results
        assert result.eligible_for_release
        assert calls == ["create", "verify", "cleanup"] and objects == {}
        assert result.results[0]["metadata"]["scenario_ref"]["version"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_import_hash_ref_forgery_and_publish_race_are_rejected(platform):
    app, _ = platform
    service = app.state.asset_service
    scenario = service.create("scenarios", draft())
    published = publish(app, scenario)
    exported = {**published, "hash": "tampered"}
    with pytest.raises(Exception) as exc:
        service.import_standard(exported)
    assert exc.value.status_code == 400
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    with pytest.raises(Exception) as exc:
        app.state.run_service.create_run(
            schema.CreateRunRequest(
                suite_id="fake",
                payload={
                    "scenario_refs": [
                        {"id": scenario["id"], "version": 1, "hash": published["hash"]}
                    ],
                },
            )
        )
    assert exc.value.status_code == 400
    repo_module = importlib.import_module("pyta_platform_backend.repositories.run_repository")
    with pytest.raises(repo_module.RunConflict):
        service.repository.publish(
            "scenarios",
            scenario["id"],
            1,
            {**scenario["draft"], "name": "wrong snapshot"},
            "race",
            "tester",
        )


def test_old_version_evidence_does_not_claim_current_risk(platform):
    app, _ = platform
    service = app.state.asset_service
    scenario = service.create("scenarios", draft())
    publish(app, scenario)
    service.repository.save_coverage(
        {
            "id": "version-risk",
            "contract_status": "confirmed",
            "contract_note": "test",
            "scenario_refs": [{"scenario_id": scenario["id"], "version": 1}],
        }
    )
    updated = service.update("scenarios", scenario["id"], 1, {**scenario["draft"], "name": "v2"})
    publish(app, updated)
    summary = service.coverage_summary()
    assert summary["verified_risks"] == 0
    assert summary["items"][0]["coverage_status"] == "version_stale"


@pytest.mark.parametrize("kind", ["scenarios", "suites"])
def test_default_asset_run_infers_environment_and_preserves_build(platform, kind):
    from fastapi.testclient import TestClient

    app, settings = platform
    service = app.state.asset_service
    scenario = service.create("scenarios", draft())
    publish(app, scenario)
    identifier = scenario["id"]
    if kind == "suites":
        suite = service.create(
            "suites",
            {"name": "same-environment", "scenarios": [{"scenario_id": identifier, "version": 1}]},
        )
        model = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest
        service.publish("suites", suite["id"], model(expected_revision=1, change_note="pin"))
        identifier = suite["id"]
    client = TestClient(app)
    response = client.post(
        f"/api/v1/{kind}/{identifier}/versions/1/runs",
        json={
            "transport_mode": "live",
            "build": "source-fixture-v1",
            "parameters": {},
        },
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    detail = app.state.run_service.get_run_detail(run_id)
    assert detail.environment_id == app.state.test_environment_id
    assert detail.environment_name == "asset-test"
    assert detail.payload["environment"]["id"] == detail.environment_id
    assert detail.payload["build"] == "source-fixture-v1"
    listed = client.get(
        "/api/v1/runs",
        params={
            "environment_id": detail.environment_id,
            "target_id": "asset-test",
            "build": "source-fixture-v1",
        },
    )
    assert listed.status_code == 200
    assert run_id in [row["run_id"] for row in listed.json()["items"]]
    assert client.get("/api/v1/runs", params={"build": "wrong-build"}).json()["total"] == 0
    wrong = client.post(
        f"/api/v1/{kind}/{identifier}/versions/1/runs",
        json={"transport_mode": "live", "environment_id": "different-environment"},
    )
    assert wrong.status_code == 400


def test_suite_rejects_mixed_environments_without_creating_a_run(platform):
    app, _ = platform
    service = app.state.asset_service
    first = service.create("scenarios", draft())
    publish(app, first)
    env_model = importlib.import_module("pyta_platform_backend.schemas.management")
    env = app.state.management_service.create_environment(
        env_model.CreateEnvironmentRequest(
            name="other", base_url="http://127.0.0.1:1", auth_mode="none"
        )
    )
    app.state.context_service.save(
        "targets",
        {
            "id": "other",
            "name": "other",
            "base_url": "http://127.0.0.1:1",
            "environment_id": env.id,
        },
        creating=True,
    )
    data = draft()
    data["target_ref"] = "other"
    second = service.create("scenarios", data)
    publish(app, second)
    suite = service.create(
        "suites",
        {
            "name": "mixed",
            "scenarios": [
                {"scenario_id": first["id"], "version": 1},
                {"scenario_id": second["id"], "version": 1},
            ],
        },
    )
    model = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest
    service.publish("suites", suite["id"], model(expected_revision=1, change_note="mixed"))
    before = app.state.run_service.list_runs().total
    with pytest.raises(Exception, match="mixed_environment"):
        service.run("suites", suite["id"], 1, request())
    assert app.state.run_service.list_runs().total == before


@pytest.mark.parametrize("ref", ["legacy-cache@1", "bootstrap-auth@1"])
def test_step_plugin_selection_without_consumer_is_rejected(platform, ref):
    from fastapi import HTTPException

    app, _ = platform
    data = draft()
    data["steps"][1]["plugin_refs"] = [ref]
    scenario = app.state.asset_service.create("scenarios", data)
    check = app.state.asset_service.preview("scenarios", scenario["id"])
    assert not check["valid"]
    assert any(item["path"].endswith("plugin_refs") for item in check["errors"])
    with pytest.raises(HTTPException) as exc:
        publish(app, scenario)
    assert exc.value.status_code == 400


def test_yanji_pack_import_is_test_only_idempotent_and_draft_only(platform):
    from fastapi.testclient import TestClient

    app, _ = platform
    context = app.state.context_service
    target = context.get("targets", "asset-test")
    identity = context.save(
        "identity-profiles",
        {
            "name": "tester",
            "target_ids": [target["id"]],
            "username_secret_ref": "env:PYTA_SECRET_YANJI_U",
            "password_secret_ref": "env:PYTA_SECRET_YANJI_P",
        },
        creating=True,
    )
    binding = context.save(
        "context-bindings",
        {
            "name": "project",
            "target_id": target["id"],
            "identity_id": identity["id"],
            "tenant_id": "test-tenant",
            "project_id": "test-project",
        },
        creating=True,
    )
    payload = {
        "target_ref": target["id"],
        "identity_ref": identity["id"],
        "binding_ref": binding["id"],
        "expected_user_id": "known-test-user",
    }
    client = TestClient(app)
    assert client.post("/api/v1/imports/yanji-query", json=payload).status_code == 400
    context.save(
        "targets",
        {
            **target,
            "base_url": "https://api-test.yanjiai.com",
            "requires_context": True,
            "auth": {"mode": "password", "contract_confirmed": True},
        },
    )
    first = client.post("/api/v1/imports/yanji-query", json=payload)
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/imports/yanji-query", json=payload)
    assert first.json()["assets"] == second.json()["assets"]
    assert first.json()["network_executed"] is False
    assert app.state.run_service.list_runs().total == 0
    for scenario in first.json()["assets"]:
        assert not app.state.asset_service.repository.versions("scenarios", scenario["id"])
        assert app.state.asset_service.preview("scenarios", scenario["id"])["valid"]
        request = scenario["draft"]["steps"][0]["request"]
        assert request["method"] == "GET"
        assert scenario["draft"]["source"]["scope"] == "query_smoke"


def test_uploaded_yaml_import_needs_no_server_source_tree(platform):
    from fastapi.testclient import TestClient

    app, _ = platform
    client = TestClient(app)
    document = """case_common: {allureEpic: imported}
query:
  host: http://localhost
  url: /health
  method: GET
  detail: imported query
  headers: {}
  requestType: JSON
  data: {}
  assert: {code: {jsonpath: $.code, type: ==, value: 200}}
"""
    response = client.post(
        "/api/v1/imports/legacy", json={"target_ref": "asset-test", "yaml_text": document}
    )
    assert response.status_code == 201, response.text
    assert response.json()["report"]["network_executed"] is False
    assert response.json()["asset"]["draft"]["source"]["path"] == "uploaded.yaml"
    invalid = client.post(
        "/api/v1/imports/legacy",
        json={"target_ref": "asset-test", "yaml_text": "private-secret: [unterminated"},
    )
    assert invalid.status_code == 400 and "private-secret" not in invalid.text

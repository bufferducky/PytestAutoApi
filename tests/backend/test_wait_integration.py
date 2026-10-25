"""R05真实本地异步服务：创建只触发一次，等待有轨迹、有终态。"""

import importlib
import json
import sys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from test_support import seed_test_environments


@pytest.fixture
def app(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    module = importlib.import_module("pyta_platform_backend.app")
    settings = importlib.import_module("pyta_platform_backend.config").BackendSettings(
        app_env="test", state_db_path=str(tmp_path / "wait.sqlite3")
    )
    return seed_test_environments(module.create_app(settings=settings))


@contextmanager
def async_service(states):
    calls = []
    states = list(states)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, data):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append("start")
            self.respond({"code": 200, "data": {"id": "task"}})

        def do_GET(self):
            calls.append("query")
            state = states.pop(0) if len(states) > 1 else states[0]
            self.respond({"code": 200, "data": {"state": state, "id": "task"}})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def scene(app, base):
    target = app.state.context_service.save(
        "targets",
        {"name": "async", "environment_id": "env-demo-mock", "base_url": base},
        creating=True,
    )
    return {
        "name": "async flow",
        "target_ref": target["id"],
        "steps": [
            {
                "step_id": "start",
                "name": "start once",
                "phase": "action",
                "operation_kind": "write",
                "contract_confirmed": True,
                "request": {"method": "POST", "url": "{{host}}/start"},
                "extractors": [{"name": "id", "selector": "data.id", "target": "outputs.start.id"}],
            },
            {
                "step_id": "wait",
                "name": "wait",
                "type": "wait_until",
                "phase": "verify",
                "operation_kind": "query",
                "contract_confirmed": True,
                "depends_on": ["start"],
                "request": {"url": "{{host}}/status/{{outputs.start.id}}"},
                "wait_policy": {
                    "contract_confirmed": True,
                    "state_selector": "data.state",
                    "state_map": {
                        "pending": "pending",
                        "running": "running",
                        "done": "succeeded",
                        "bad": "failed",
                    },
                    "interval_seconds": 0,
                    "max_attempts": 4,
                    "deadline_seconds": 2,
                },
                "assertions": [
                    {"name": "same task", "selector": "data.id", "expected_ref": "outputs.start.id"}
                ],
            },
        ],
    }


@pytest.mark.parametrize(
    ("states", "status", "queries"),
    [
        (["pending", "running", "done"], "succeeded", 3),
        (["pending", "bad"], "failed", 2),
        (["pending", "weird"], "error", 2),
        (["pending"], "timed_out", 4),
    ],
)
def test_real_async_service_trigger_once_and_persist_trace(app, states, status, queries):
    with async_service(states) as (base, calls):
        data = scene(app, base)
        service = app.state.asset_service
        created = service.create("scenarios", data)
        model = importlib.import_module("pyta_platform_backend.schemas.assets")
        service.publish(
            "scenarios",
            created["id"],
            model.PublishRequest(expected_revision=1, change_note="wait"),
        )
        run = service.run(
            "scenarios", created["id"], 1, model.AssetRunRequest(transport_mode="live")
        )
        result = app.state.worker_runner.run_next()
        assert result.status.value == status, result.status_message
        assert calls.count("start") == 1 and calls.count("query") == queries
        waiting = next(case for case in result.results if case["case_id"] == "s0__wait")["steps"][0]
        assert waiting["poll_attempts"] == queries
        assert waiting["poll_trace"][-1]["raw_state"] == states[-1]
        assert waiting["response"]["body"]["data"]["id"] == "task"
        assert result.counts["requests"] == 1 + queries
        assert result.run_id == run.run_id


def test_publish_rejects_invalid_selector_unknown_rule_and_unconfirmed_adapter(app):
    with async_service(["done"]) as (base, calls):
        data = scene(app, base)
        data["steps"][1]["assertions"][0]["selector"] = "data.[invalid"
        data["steps"][1]["assertions"][0]["rule_ref"] = "unknown@1"
        data["steps"][1]["wait_policy"]["contract_confirmed"] = False
        created = app.state.asset_service.create("scenarios", data)
        check = app.state.asset_service.preview("scenarios", created["id"])
        assert not check["valid"]
        assert any("selector" in e["path"] for e in check["errors"])
        assert any("rule_ref" in e["path"] for e in check["errors"])
        assert any("wait_policy" in e["path"] for e in check["errors"])
        assert not calls


def test_invalid_json_response_is_executor_error_not_assertion_failure(app):
    import httpx

    from testflow_engine import AssertionSpec, HttpxTransport, RequestSpec
    from testflow_engine import TestCaseDefinition as Case
    from testflow_engine import TestFlowEngine as Engine
    from testflow_engine import TestRunDefinition as Run

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Type": "application/json"}, text="not json"
            )
        )
    )
    try:
        result = Engine(transport=HttpxTransport(client)).execute_run(
            Run(
                cases=[
                    Case(
                        case_id="json",
                        title="json",
                        request=RequestSpec(url="https://example.test"),
                        assertions=[AssertionSpec(name="code", selector="code", expected=200)],
                    )
                ]
            )
        )
        assert result.status.value == "error" and "JSON" in result.cases[0].error
    finally:
        client.close()

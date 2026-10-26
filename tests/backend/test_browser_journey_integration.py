"""独立下载的Chromium与本地合成页面；不是公司Web/App业务验收。"""

import importlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from test_support import seed_test_environments

pytestmark = pytest.mark.skipif(
    os.environ.get("PYTA_RUN_BROWSER_TESTS") != "1",
    reason="真实浏览器独立检查，需显式启用与安装Chromium",
)


def test_real_chromium_journey_isolated_storage_failure_artifact_and_baseline(tmp_path):
    from playwright.sync_api import sync_playwright

    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    module = importlib.import_module("pyta_platform_backend.app")
    app = module.create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "browser.sqlite3")
        )
    )
    seed_test_environments(app)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        version = browser.version
        browser.close()

    objects = {}

    class Handler(BaseHTTPRequestHandler):
        def json_response(self, data):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            objects[body["name"]] = {"id": body["name"]}
            self.json_response({"code": 200, "data": objects[body["name"]]})

        def do_DELETE(self):
            objects.pop(self.path.split("/")[-1], None)
            self.json_response({"code": 200})

        def do_GET(self):
            if self.path.startswith("/objects/"):
                self.json_response({"code": 200, "data": objects.get(self.path.split("/")[-1], {})})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html;charset=utf-8")
            self.end_headers()
            self.wfile.write(
                """<!doctype html><html><body>
<label>测试名称<input id="name" placeholder="请输入测试名称"></label><button id="save">保存</button>
<div data-testid="result"></div>
<script>
const output=document.querySelector('[data-testid=result]');
output.textContent=localStorage.getItem('state') || 'fresh';
document.getElementById('save').onclick=()=>{
output.textContent=document.getElementById('name').value;
localStorage.setItem('state',output.textContent);};
</script></body></html>""".encode()
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = app.state.context_service.save(
            "targets",
            {
                "name": "synthetic browser",
                "environment_id": "env-demo-mock",
                "base_url": f"http://127.0.0.1:{server.server_port}",
            },
            creating=True,
        )
        data = {
            "name": "真实Chromium本地机制",
            "runner_type": "web",
            "target_ref": target["id"],
            "chromium_version": version,
            "contract_confirmed": True,
            "synthetic_test_data": True,
            "actions": [
                {"step_id": "open", "name": "open", "action": "navigate", "path": "/"},
                {
                    "step_id": "fill",
                    "name": "fill",
                    "action": "fill",
                    "selector": {"strategy": "placeholder", "value": "请输入测试名称"},
                    "value": "synthetic-first",
                },
                {
                    "step_id": "save",
                    "name": "save",
                    "action": "click",
                    "selector": {"strategy": "role", "value": "button", "name": "保存"},
                },
                {
                    "step_id": "assert",
                    "name": "assert",
                    "action": "assert_text",
                    "selector": {"strategy": "testid", "value": "result"},
                    "value": "synthetic-first",
                },
            ],
        }
        first = app.state.journey_service.define(data)
        created = app.state.journey_service.run(first["id"], 1)
        result = app.state.worker_runner.run_next()
        assert result.run_id == created.run_id and result.status.value == "succeeded", (
            result.status_message
        )
        assert result.counts["assertions"] == 1 and result.counts["executed"] == 4
        isolated = {
            **data,
            "name": "isolated",
            "actions": [data["actions"][0], {**data["actions"][-1], "value": "fresh"}],
        }
        second = app.state.journey_service.define(isolated)
        app.state.journey_service.run(second["id"], 1)
        assert app.state.worker_runner.run_next().status.value == "succeeded"
        failure = {
            **isolated,
            "name": "failure screenshot",
            "actions": [
                data["actions"][0],
                {**data["actions"][-1], "value": "wrong", "timeout_seconds": 0.2},
            ],
        }
        third = app.state.journey_service.define(failure)
        failed_run = app.state.journey_service.run(third["id"], 1)
        failed = app.state.worker_runner.run_next()
        assert failed.status.value == "failed"
        refs = app.state.diagnostic_service.artifacts.list(failed_run.run_id)
        assert len(refs) == 1 and refs[0]["step_id"] == "assert"
        _, content = app.state.diagnostic_service.artifact(
            refs[0]["artifact_id"], failed_run.run_id, download=True
        )
        assert content.startswith(b"\x89PNG")
        mismatch = app.state.journey_service.define(
            {**isolated, "chromium_version": "wrong-baseline"}
        )
        app.state.journey_service.run(mismatch["id"], 1)
        assert app.state.worker_runner.run_next().status.value == "blocked"
        fixture = app.state.resource_service.define(
            {
                "name": "browser object",
                "strategy": "create",
                "contract_confirmed": True,
                "acquire_request": {
                    "method": "POST",
                    "url": "{{host}}/objects",
                    "body": {"name": "{{runtime.test_prefix}}"},
                },
                "release_request": {
                    "method": "DELETE",
                    "url": "{{host}}/objects/{{fixtures.item.id}}",
                },
            }
        )
        fixture_data = {
            **data,
            "capture_trace": True,
            "capture_video": True,
            "name": "browser fixture readback",
            "fixtures": [{"name": "item", "definition_id": fixture["id"], "version": 1}],
            "actions": [
                data["actions"][0],
                {**data["actions"][1], "value": None, "value_ref": "fixtures.item.id"},
                data["actions"][2],
                {**data["actions"][3], "value": None, "value_ref": "fixtures.item.id"},
                {
                    "step_id": "api-check",
                    "name": "same object API",
                    "action": "api_assert",
                    "request": {"url": "{{host}}/objects/{{fixtures.item.id}}"},
                    "assertions": [
                        {
                            "name": "same object",
                            "selector": "data.id",
                            "expected_ref": "fixtures.item.id",
                        }
                    ],
                },
            ],
        }
        prepared = app.state.journey_service.define(fixture_data)
        fixture_run = app.state.journey_service.run(prepared["id"], 1)
        fixture_result = app.state.worker_runner.run_next()
        assert fixture_result.status.value == "succeeded", fixture_result.status_message
        assert fixture_result.counts["requests"] == 1 and fixture_result.counts["assertions"] == 2
        assert fixture_result.cleanup_status == "succeeded" and not objects
        records = app.state.resource_service.repository.resources(fixture_run.run_id)
        assert len(records) == 1 and records[0]["state"] == "released"
        captured = app.state.diagnostic_service.artifacts.list(fixture_run.run_id)
        assert {a["content_type"] for a in captured} == {
            "application/vnd.playwright.trace+zip",
            "video/webm",
        }
        for item in captured:
            _, recording = app.state.diagnostic_service.artifact(
                item["artifact_id"], fixture_run.run_id, download=True
            )
            assert recording and item["step_id"] == "api-check"
        assert (
            fixture_result.results[-1]["steps"][0]["assertions"][0]["actual"]
            == records[0]["object_id"]
        )
        report = {
            "scope": "本地合成页面与真实Chromium；不代表公司业务/Android",
            "chromium_version": version,
            "isolated_contexts": True,
            "assertion_count": result.counts["assertions"],
            "failure_png_step_link": refs[0]["step_id"],
            "wrong_baseline": "blocked",
            "fixture_ui_api_cleanup": True,
            "native_trace_and_video": True,
        }
        print(json.dumps(report, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

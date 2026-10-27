import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi.testclient import TestClient
from pyta_platform_backend.app import create_app
from pyta_platform_backend.config import BackendSettings

requests = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"code":200}')

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
settings = BackendSettings(
    app_env="test",
    state_db_path="/tmp/worker-check.sqlite3",
    artifact_root="/tmp/worker-check-artifacts",
)
app = create_app(settings=settings)
try:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/runs",
            json={
                "suite_id": "release-local-smoke",
                "requested_by": "deployment-check",
                "payload": {
                    "execution_mode": "standard_run",
                    "transport_mode": "live",
                    "run_definition": {
                        "cases": [
                            {
                                "case_id": "local-http",
                                "title": "Container-local HTTP",
                                "request": {"url": f"http://127.0.0.1:{server.server_port}/check"},
                                "assertions": [
                                    {"name": "business-code", "selector": "code", "expected": 200}
                                ],
                            }
                        ]
                    },
                },
            },
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            detail = client.get("/api/v1/runs/" + run_id).json()
            if detail["status"] not in ("queued", "running"):
                break
            time.sleep(0.1)
        assert detail["status"] == "succeeded", detail.get("status_message")
        assert detail["counts"]["assertions"] == 1
        assert detail["counts"]["requests"] == 1
        assert len(requests) == 1
    restarted = create_app(settings=settings)
    retained = restarted.state.run_service.get_run_detail(run_id)
    assert retained.status.value == "succeeded"
    assert len(retained.results) == 1
    print(
        json.dumps(
            {
                "status": "succeeded",
                "requests": 1,
                "assertions": 1,
                "results_survive_app_recreation": True,
                "storage": "isolated_container_sqlite",
                "production_database_touched": False,
                "company_business_requests_executed": False,
            }
        )
    )
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

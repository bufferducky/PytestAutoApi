"""框架审查探针：仅临时SQLite与127.0.0.1；不读取凭证、不调用公司服务。"""

import json
import os
import sys
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "platform/backend/src")]


def probe_asset_scope():
    from pyta_platform_backend.app import create_app
    from pyta_platform_backend.config import BackendSettings
    from pyta_platform_backend.schemas.assets import AssetRunRequest, PublishRequest
    from pyta_platform_backend.services.scenario_compiler import compile_scenario

    with TemporaryDirectory(prefix="pyta-audit-") as directory:
        app = create_app(
            BackendSettings(
                app_env="test",
                state_db_path=str(Path(directory) / "state.db"),
                artifact_root=str(Path(directory) / "artifacts"),
            )
        )
        management = app.state.management_service._repository
        env = management.create_environment(
            name="audit",
            base_url="http://127.0.0.1:1",
            auth_mode="none",
            status="draft",
            variables={},
        )
        target = app.state.context_service.save(
            "targets",
            {"name": "audit", "environment_id": env.id, "base_url": env.base_url},
            creating=True,
        )
        assets = app.state.asset_service
        draft = assets.create(
            "scenarios",
            {
                "name": "audit",
                "target_ref": target["id"],
                "steps": [
                    {
                        "step_id": "read",
                        "name": "read",
                        "request": {"url": "{{host}}/check"},
                        "contract_confirmed": True,
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    }
                ],
            },
        )
        published = assets.publish(
            "scenarios", draft["id"], PublishRequest(expected_revision=1, change_note="audit")
        )
        created = assets.run(
            "scenarios", draft["id"], published["version"], AssetRunRequest(transport_mode="live")
        )
        detail = app.state.run_service.get_run_detail(created.run_id)
        observed = {
            "run_environment_id": detail.environment_id,
            "snapshot_environment_id": detail.payload["context_snapshots"]["default"]["target"][
                "environment_id"
            ],
            "build": detail.payload["build"],
            "status": detail.status.value,
            "business_requests": 0,
        }
        assert observed["run_environment_id"] is None
        assert observed["snapshot_environment_id"] == env.id
        assert observed["build"] == "unspecified"
        # 插件声明能通过发布校验，但编译产物与未声明插件的版本没有差异。
        plain = deepcopy(published)
        declared = deepcopy(published)
        declared["data"]["steps"][0]["plugin_refs"] = ["bootstrap-auth@1"]
        a = compile_scenario(plain, scope_id="s0").model_dump()
        b = compile_scenario(declared, scope_id="s0").model_dump()
        a.pop("run_id")
        b.pop("run_id")
        assert a == b
        return observed, {
            "declared_plugin": "bootstrap-auth@1",
            "compiled_definition_identical": a == b,
        }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = json.dumps(
            {"code": 200, "data": {"tenantId": "other-tenant", "projectId": "other-project"}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def probe_context_truth():
    from pyta_platform_backend.app import create_app
    from pyta_platform_backend.config import BackendSettings
    from pyta_platform_backend.schemas.context import PreflightRequest

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # 通过真实服务保存合法的目标/身份/绑定，避免用非法快照制造反例。
        with TemporaryDirectory(prefix="pyta-audit-context-") as directory:
            app = create_app(
                BackendSettings(
                    app_env="test",
                    state_db_path=str(Path(directory) / "state.db"),
                    artifact_root=str(Path(directory) / "artifacts"),
                )
            )
            base_url = f"http://127.0.0.1:{server.server_port}"
            environment = app.state.management_service._repository.create_environment(
                name="audit-context",
                base_url=base_url,
                auth_mode="none",
                status="draft",
                variables={},
            )
            service = app.state.context_service
            target = service.save(
                "targets",
                {
                    "name": "audit",
                    "environment_id": environment.id,
                    "base_url": base_url,
                    "requires_context": True,
                    "checks": [
                        {
                            "name": "code-only-check",
                            "path": "/check",
                            "query_contract_confirmed": True,
                        }
                    ],
                },
                creating=True,
            )
            identity = service.save(
                "identity-profiles",
                {
                    "name": "synthetic-audit",
                    "target_ids": [target["id"]],
                    "username_secret_ref": "env:PYTA_SECRET_AUDIT_USER",
                    "password_secret_ref": "env:PYTA_SECRET_AUDIT_PASSWORD",
                },
                creating=True,
            )
            binding = service.save(
                "context-bindings",
                {
                    "name": "audit-binding",
                    "target_id": target["id"],
                    "identity_id": identity["id"],
                    "tenant_id": "expected-tenant",
                    "project_id": "expected-project",
                },
                creating=True,
            )
            with patch.dict(
                os.environ,
                {
                    "PYTA_SECRET_AUDIT_USER": "synthetic-user",
                    "PYTA_SECRET_AUDIT_PASSWORD": "synthetic-value",
                },
            ):
                observed = service.preflight(
                    environment.id,
                    PreflightRequest(
                        target_id=target["id"],
                        identity_id=identity["id"],
                        context_binding_id=binding["id"],
                        execute_login=True,
                    ),
                )
        assert observed["context"] == "passed"
        return {
            "actual_response_scope": "other-tenant/other-project",
            "expected_scope": "expected-tenant/expected-project",
            "tenant_path": target["checks"][0]["tenant_path"],
            "project_path": target["checks"][0]["project_path"],
            "preflight": observed,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main():
    scope, plugins = probe_asset_scope()
    print(
        json.dumps(
            {
                "asset_run_missing_scope": scope,
                "declared_plugin_discarded": plugins,
                "context_without_ownership_assertion": probe_context_truth(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

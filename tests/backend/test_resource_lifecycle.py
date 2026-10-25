"""R04：资源所有权/反序清理、租约竞争与中断、固定媒体校验。"""

import hashlib
import importlib
import json
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest
from test_support import seed_test_environments


@pytest.fixture
def platform(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    module = importlib.import_module("pyta_platform_backend.app")
    settings = importlib.import_module("pyta_platform_backend.config").BackendSettings(
        app_env="test", state_db_path=str(tmp_path / "resources.sqlite3")
    )
    return seed_test_environments(module.create_app(settings=settings)), settings


@contextmanager
def server():
    objects, calls = {}, []
    behavior = {
        "cleanup_fail": False,
        "create_missing_id": False,
        "slow_entered": Event(),
        "slow_release": Event(),
    }

    class Handler(BaseHTTPRequestHandler):
        def answer(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/objects":
                identifier = body["name"]
                objects[identifier] = body
                calls.append(("create", identifier))
                self.answer(
                    {
                        "code": 200,
                        "data": {} if behavior["create_missing_id"] else {"id": identifier},
                    }
                )
            else:
                self.answer({"code": 500})

        def do_GET(self):
            if self.path == "/slow":
                behavior["slow_entered"].set()
                behavior["slow_release"].wait(5)
            if self.path == "/delay":
                Event().wait(0.3)
            identifier = self.path.split("/")[-1]
            calls.append(("read", identifier))
            self.answer({"code": 200, "data": objects.get(identifier, {"missing": True})})

        def do_PUT(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.startswith("/upload"):
                calls.append(("upload", len(raw)))
                self.answer({"code": 200})
                return
            identifier = self.path.split("/")[-1]
            objects[identifier] = json.loads(raw)
            calls.append(("update", identifier))
            self.answer({"code": 200})

        def do_DELETE(self):
            identifier = self.path.split("/")[-1]
            calls.append(("delete", identifier))
            if behavior["cleanup_fail"]:
                self.answer({"code": 500})
            else:
                objects.pop(identifier, None)
                self.answer({"code": 200})

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", objects, calls, behavior
    finally:
        behavior["slow_release"].set()
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


def asset(app, base, *, strategy="create", object_id=None, pool_id=None, two=False, fail=False):
    target = app.state.context_service.save(
        "targets",
        {"name": "local", "environment_id": "env-demo-mock", "base_url": base},
        creating=True,
    )
    resource = app.state.resource_service.define(
        {
            "name": "object",
            "strategy": strategy,
            "contract_confirmed": True,
            "pool_id": pool_id,
            "object_id": object_id,
            "restore_required": False,
            "acquire_request": {
                "method": "POST",
                "url": "{{host}}/objects",
                "body": {"name": "{{runtime.test_prefix}}-item"},
            },
            "release_request": {"method": "DELETE", "url": "{{host}}/objects/{{fixtures.item.id}}"},
        }
    )
    requirements = [{"name": "item", "definition_id": resource["id"], "version": 1}]
    if two:
        other = app.state.resource_service.define(
            {
                "name": "child",
                "strategy": "create",
                "contract_confirmed": True,
                "acquire_request": {
                    "method": "POST",
                    "url": "{{host}}/objects",
                    "body": {
                        "name": "{{runtime.test_prefix}}-child",
                        "parent": "{{fixtures.item.id}}",
                    },
                },
                "release_request": {
                    "method": "DELETE",
                    "url": "{{host}}/objects/{{fixtures.child.id}}",
                },
            }
        )
        requirements.append(
            {"name": "child", "definition_id": other["id"], "version": 1, "depends_on": ["item"]}
        )
    created = app.state.asset_service.create(
        "scenarios",
        {
            "name": "fixtures",
            "target_ref": target["id"],
            "fixtures": requirements,
            "steps": [
                {
                    "step_id": "read",
                    "name": "read",
                    "request": {"url": "{{host}}/objects/{{fixtures.item.id}}"},
                    "contract_confirmed": True,
                    "assertions": [
                        {"name": "code", "selector": "code", "expected": 500 if fail else 200}
                    ],
                }
            ],
        },
    )
    publish = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest(
        expected_revision=1, change_note="resource test"
    )
    app.state.asset_service.publish("scenarios", created["id"], publish)
    return target, resource, created


def run(app, created):
    req = importlib.import_module("pyta_platform_backend.schemas.assets").AssetRunRequest(
        transport_mode="live"
    )
    created_run = app.state.asset_service.run("scenarios", created["id"], 1, req)
    detail = app.state.worker_runner.run_next()
    return created_run, detail


def test_ten_runs_unique_resources_and_reverse_dependency_cleanup(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        target, definition, scenario = asset(app, base, two=True)
        ids = []
        for _ in range(10):
            created, detail = run(app, scenario)
            assert detail.status.value == "succeeded" and detail.cleanup_status == "succeeded", (
                detail.status_message
            )
            records = app.state.resource_service.repository.resources(created.run_id)
            assert len(records) == 2 and all(r["state"] == "released" for r in records)
            by_fixture = {record["fixture_id"]: record for record in records}
            ids.append(by_fixture["item"]["object_id"])
            assert calls[-2:] == [
                ("delete", by_fixture["child"]["object_id"]),
                ("delete", by_fixture["item"]["object_id"]),
            ]
            assert not objects
        assert len(set(ids)) == 10


def test_assertion_failure_still_cleans_and_cleanup_failure_preserves_pending(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base, fail=True)
        created, detail = run(app, scenario)
        assert detail.status.value == "failed" and not objects
        behavior["cleanup_fail"] = True
        second, detail = run(app, scenario)
        assert detail.status.value == "failed" and detail.cleanup_status == "cleanup_failed"
        assert not detail.eligible_for_release
        resources = app.state.resource_service.repository.resources(second.run_id)
        assert resources[0]["state"] == "cleanup_failed"
        plan = app.state.resource_service.cleanup_preflight(second.run_id)
        assert plan["ready"] == [resources[0]["id"]] and not plan["network_executed"]
        behavior["cleanup_fail"] = False
        result = app.state.resource_service.cleanup(second.run_id, plan["preflight_token"])
        assert result["results"][0]["state"] == "released" and not objects


def test_unknown_creation_id_never_guesses_cleanup(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base)
        behavior["create_missing_id"] = True
        created, detail = run(app, scenario)
        assert detail.status.value == "error"
        assert detail.cleanup_status == "cleanup_failed"
        record = app.state.resource_service.repository.resources(created.run_id)[0]
        assert record["state"] == "ownership_unknown"
        assert all(call[0] != "delete" for call in calls)
        assert app.state.resource_service.cleanup_preflight(created.run_id)["blocked"] == [
            record["id"]
        ]


def test_pool_atomic_claim_expiry_generation_and_owner_protection(platform):
    app, settings = platform
    service = app.state.resource_service
    app.state.context_service.save(
        "targets",
        {
            "id": "test-target",
            "name": "pool-test",
            "environment_id": "env-demo-mock",
            "base_url": "https://example.test",
        },
        creating=True,
    )
    context = {"target_id": "test-target", "tenant_id": "t", "project_id": "p"}
    service.add_pool(
        {"pool_id": "device", "object_id": "device1", **context, "dedicated_test_resource": True}
    )
    module = importlib.import_module("pyta_platform_backend.repositories.resource_repository")
    repos = [module.ResourceRepository(settings.state_db_path) for _ in range(2)]

    def claim(pair):
        index, repo = pair
        try:
            return repo.lease("device", "owner" + str(index), context, 300)
        except ValueError:
            return None

    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(claim, enumerate(repos)))
    winner = next(c for c in claims if c)
    assert sum(c is not None for c in claims) == 1
    assert repos[0].renew(winner, 600)["expires_at"] > winner["expires_at"]
    with pytest.raises(ValueError):
        repos[0].release_lease({**winner, "owner": "someone-else"})
    with repos[0].transaction():
        repos[0]._connection.execute(
            "UPDATE resource_pool SET expires_at=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),),
        )
    with pytest.raises(ValueError):
        repos[0].lease("device", "next-owner", context, 300)
    assert repos[0].pool()[0]["state"] == "needs_reconciliation"
    with pytest.raises(ValueError):
        repos[0].check_lease(winner)
    repos[0].release_lease(winner)
    new = repos[0].lease("device", "new-owner", context, 300)
    assert new["generation"] > winner["generation"]
    with pytest.raises(ValueError):
        repos[0].release_lease(winner)


def test_read_only_exact_object_is_not_modified_and_write_publish_is_rejected(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        target, definition, scenario = asset(
            app, base, strategy="read_only", object_id="known", pool_id="readonly"
        )
        objects["known"] = {"name": "known"}
        app.state.resource_service.add_pool(
            {
                "pool_id": "readonly",
                "object_id": "known",
                "target_id": target["id"],
                "tenant_id": "",
                "project_id": "",
                "dedicated_test_resource": True,
            }
        )
        created, detail = run(app, scenario)
        assert detail.status.value == "succeeded" and objects == {"known": {"name": "known"}}
        data = scenario["draft"]
        data["steps"][0]["operation_kind"] = "write"
        app.state.asset_service.update("scenarios", scenario["id"], 1, data)
        assert not app.state.asset_service.preview("scenarios", scenario["id"])["valid"]
        assert all(action != "delete" for action, _ in calls)


def test_media_manifest_hash_duration_size_and_directory_validation(platform, tmp_path):
    app, _ = platform
    service = app.state.resource_service
    service.media_root = tmp_path / "media"
    service.media_root.mkdir()
    path = service.media_root / "fixture.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    data = {
        "name": "synthetic",
        "path": "fixture.wav",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "byte_size": path.stat().st_size,
        "duration_seconds": 0.1,
        "format": "wav",
        "language": "zh",
        "noise": "none",
        "source": "synthesized locally",
        "authorized": True,
        "redacted": True,
        "applicable_scenarios": ["test"],
    }
    saved = service.media(data)
    assert service.media_preflight(saved["id"], 1)["upload_contract"] == "not_verified"
    for changes in [
        {"sha256": "wrong"},
        {"duration_seconds": 99},
        {"path": "../outside.wav"},
        {"byte_size": 1},
        {"authorized": False},
    ]:
        with pytest.raises(Exception) as exc:
            service.media({**data, **changes})
        assert exc.value.status_code == 400


def test_resource_owner_mismatch_and_restart_reconciliation(platform):
    app, settings = platform
    from pyta_platform_backend.workers.resource_plugin import cleanup_record

    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base)
        behavior["cleanup_fail"] = True
        created, detail = run(app, scenario)
        record = app.state.resource_service.repository.resources(created.run_id)[0]
        with pytest.raises(ValueError):
            cleanup_record(
                app.state.resource_service.repository, {**record, "context": {"target_id": "wrong"}}
            )
        resource = app.state.resource_service.repository
        record["state"] = "in_use"
        resource.put_resource(record)
        module = importlib.import_module("pyta_platform_backend.app")
        restarted = module.create_app(settings=settings)
        restarted.state.resource_service.repository.reconcile(set())
        recovered = restarted.state.resource_service.repository.resources(created.run_id)[0]
        assert recovered["state"] == "needs_reconciliation"
        with pytest.raises(Exception) as exc:
            restarted.state.resource_service.confirm_reconciled(
                created.run_id, "wrong-resource", "verified manually"
            )
        assert exc.value.status_code == 404


def test_lease_snapshots_original_and_restores_instead_of_deleting(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        target = app.state.context_service.save(
            "targets",
            {"name": "borrow", "environment_id": "env-demo-mock", "base_url": base},
            creating=True,
        )
        objects["borrowed"] = {"name": "original"}
        app.state.resource_service.add_pool(
            {
                "pool_id": "borrow",
                "object_id": "borrowed",
                "target_id": target["id"],
                "tenant_id": "",
                "project_id": "",
                "dedicated_test_resource": True,
            }
        )
        definition = app.state.resource_service.define(
            {
                "name": "borrow",
                "strategy": "lease",
                "contract_confirmed": True,
                "pool_id": "borrow",
                "restore_required": True,
                "snapshot_request": {"url": "{{host}}/objects/{{fixtures.item.id}}"},
                "release_request": {
                    "method": "PUT",
                    "url": "{{host}}/objects/{{fixtures.item.id}}",
                    "body": "{{fixtures.item.original.data}}",
                },
            }
        )
        scene = app.state.asset_service.create(
            "scenarios",
            {
                "name": "restore",
                "target_ref": target["id"],
                "fixtures": [{"name": "item", "definition_id": definition["id"], "version": 1}],
                "steps": [
                    {
                        "step_id": "change",
                        "name": "change",
                        "phase": "action",
                        "operation_kind": "write",
                        "contract_confirmed": True,
                        "request": {
                            "method": "PUT",
                            "url": "{{host}}/objects/{{fixtures.item.id}}",
                            "body": {"name": "changed"},
                        },
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    }
                ],
            },
        )
        publish = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest(
            expected_revision=1, change_note="restore"
        )
        app.state.asset_service.publish("scenarios", scene["id"], publish)
        created, result = run(app, scene)
        assert result.status.value == "succeeded" and result.cleanup_status == "succeeded"
        assert objects["borrowed"] == {"name": "original"}
        assert all(action != "delete" for action, _ in calls)
        assert app.state.resource_service.repository.pool()[0]["state"] == "available"


def test_second_fixture_error_cleans_first_and_reports_missing_contract(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base, two=True)
        data = scenario["draft"]
        # 固定已确认但故意返回错误的第二provider，验证部分成功的清理路径。
        requirement = data["fixtures"][1]
        definition = app.state.resource_service.fixture(requirement["definition_id"], 1)
        app.state.resource_service.define(
            {
                **definition["data"],
                "id": definition["id"],
                "acquire_request": {
                    "method": "POST",
                    "url": "{{host}}/fail",
                    "body": {"name": "test"},
                },
            }
        )
        data["fixtures"][1]["version"] = 2
        app.state.asset_service.update("scenarios", scenario["id"], 1, data)
        pub = importlib.import_module("pyta_platform_backend.schemas.assets").PublishRequest(
            expected_revision=2, change_note="partial"
        )
        app.state.asset_service.publish("scenarios", scenario["id"], pub)
        req = importlib.import_module("pyta_platform_backend.schemas.assets").AssetRunRequest(
            transport_mode="live"
        )
        created = app.state.asset_service.run("scenarios", scenario["id"], 2, req)
        result = app.state.worker_runner.run_next()
        assert result.status.value == "error" and not objects
        records = app.state.resource_service.repository.resources(created.run_id)
        by_fixture = {record["fixture_id"]: record for record in records}
        assert by_fixture["item"]["state"] == "released"
        assert by_fixture["child"]["state"] == "ownership_unknown"
        assert result.cleanup_status == "cleanup_failed"


def test_manual_cleanup_preflight_token_cannot_be_reused_after_state_change(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base)
        behavior["cleanup_fail"] = True
        created, _ = run(app, scenario)
        plan = app.state.resource_service.cleanup_preflight(created.run_id)
        record = app.state.resource_service.repository.resources(created.run_id)[0]
        record["state"] = "needs_reconciliation"
        app.state.resource_service.repository.put_resource(record)
        with pytest.raises(Exception) as exc:
            app.state.resource_service.cleanup(created.run_id, plan["preflight_token"])
        assert exc.value.status_code == 409


def test_media_upload_requires_contract_and_never_returns_signed_url(platform, tmp_path):
    app, _ = platform
    service = app.state.resource_service
    service.media_root = tmp_path / "media"
    service.media_root.mkdir()
    path = service.media_root / "upload.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    item = service.media(
        {
            "name": "upload",
            "path": "upload.wav",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "byte_size": path.stat().st_size,
            "duration_seconds": 0.1,
            "format": "wav",
            "language": "zh",
            "noise": "none",
            "source": "local synthesis",
            "authorized": True,
            "redacted": True,
            "applicable_scenarios": ["upload-test"],
        }
    )
    with server() as (base, objects, calls, behavior):
        target = app.state.context_service.save(
            "targets",
            {"name": "upload", "environment_id": "env-demo-mock", "base_url": base},
            creating=True,
        )
        kwargs = {
            "signed_url": base + "/upload?signature=upload-secret-sentinel",
            "target_id": target["id"],
            "context_service": app.state.context_service,
        }
        with pytest.raises(ValueError):
            service.upload_media(item["id"], 1, contract_confirmed=False, **kwargs)
        assert calls == []
        result = service.upload_media(item["id"], 1, contract_confirmed=True, **kwargs)
        assert result["uploaded"] and calls == [("upload", path.stat().st_size)]
        assert "signature" not in json.dumps(result) and "upload-secret-sentinel" not in json.dumps(
            result
        )


@pytest.mark.parametrize("stop_kind", ["cancel", "timeout"])
def test_stopped_main_flow_still_releases_created_fixture(platform, stop_kind):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scene = asset(app, base)
        data = scene["draft"]
        data["steps"][0]["request"]["url"] = "{{host}}/" + (
            "slow" if stop_kind == "cancel" else "delay"
        )
        app.state.asset_service.update("scenarios", scene["id"], 1, data)
        model = importlib.import_module("pyta_platform_backend.schemas.assets")
        app.state.asset_service.publish(
            "scenarios",
            scene["id"],
            model.PublishRequest(expected_revision=2, change_note="stop test"),
        )
        request = model.AssetRunRequest(transport_mode="live")
        plan = app.state.asset_service.plan("scenarios", scene["id"], 2, request)
        plan["timeout_seconds"] = 5 if stop_kind == "cancel" else 0.15
        schema = importlib.import_module("pyta_platform_backend.schemas.run")
        created = app.state.run_service._create_prepared(
            schema.CreateRunRequest(suite_id="stop-resource", payload=plan), None
        )
        if stop_kind == "cancel":
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(app.state.worker_runner.run_next)
                assert behavior["slow_entered"].wait(2)
                app.state.run_service.cancel_run(created.run_id)
                behavior["slow_release"].set()
                result = future.result(timeout=5)
        else:
            result = app.state.worker_runner.run_next()
        assert result.status.value == ("cancelled" if stop_kind == "cancel" else "timed_out")
        assert result.cleanup_status == "succeeded"
        assert not objects
        assert all(
            r["state"] == "released"
            for r in app.state.resource_service.repository.resources(created.run_id)
        )


def test_same_definition_in_two_scenarios_produces_separate_objects_and_dry_run_is_readonly(
    platform,
):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, definition, scene = asset(app, base)
        second = app.state.asset_service.create("scenarios", {**scene["draft"], "name": "second"})
        model = importlib.import_module("pyta_platform_backend.schemas.assets")
        app.state.asset_service.publish(
            "scenarios",
            second["id"],
            model.PublishRequest(expected_revision=1, change_note="second"),
        )
        suite = app.state.asset_service.create(
            "suites",
            {
                "name": "two",
                "scenarios": [
                    {"scenario_id": scene["id"], "version": 1},
                    {"scenario_id": second["id"], "version": 1},
                ],
            },
        )
        app.state.asset_service.publish(
            "suites", suite["id"], model.PublishRequest(expected_revision=1, change_note="two")
        )
        request = model.AssetRunRequest(transport_mode="live")
        preview = app.state.asset_service.plan("suites", suite["id"], 1, request)
        assert preview["resource_actions"]["s0"]["network_executed"] is False
        assert not calls
        created = app.state.asset_service.run("suites", suite["id"], 1, request)
        result = app.state.worker_runner.run_next()
        assert result.status.value == "succeeded" and not objects
        records = app.state.resource_service.repository.resources(created.run_id)
        assert len({r["object_id"] for r in records}) == 2


def test_no_dedicated_pool_resource_is_blocked_not_first_record_fallback(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base, strategy="lease", pool_id="empty")
        created, detail = run(app, scenario)
        assert detail.status.value == "blocked"
        assert calls == [] and not detail.eligible_for_release
        assert (
            app.state.resource_service.repository.resources(created.run_id)[0]["object_id"] is None
        )


def test_unknown_provider_and_unconfirmed_contract_cannot_publish(platform):
    app, _ = platform
    with pytest.raises(Exception) as exc:
        app.state.resource_service.define(
            {
                "name": "unknown",
                "strategy": "read_only",
                "provider_ref": "eval@9",
                "pool_id": "test",
                "object_id": "test",
            }
        )
    assert exc.value.status_code == 400
    definition = app.state.resource_service.define(
        {"name": "unconfirmed", "strategy": "read_only", "pool_id": "test", "object_id": "test"}
    )
    scene = app.state.asset_service.create(
        "scenarios",
        {
            "name": "blocked",
            "target_ref": "default-env-demo-mock",
            "fixtures": [{"name": "test", "definition_id": definition["id"], "version": 1}],
            "steps": [
                {
                    "step_id": "read",
                    "name": "read",
                    "request": {"url": "{{host}}/objects/{{fixtures.test.id}}"},
                    "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                }
            ],
        },
    )
    check = app.state.asset_service.preview("scenarios", scene["id"])
    assert not check["valid"] and any(e["path"] == "fixtures.0" for e in check["errors"])


def test_actual_worker_process_crash_leaves_recoverable_owned_resource(platform):
    import os
    import subprocess
    from pathlib import Path

    from fastapi.testclient import TestClient

    app, settings = platform
    with server() as (base, objects, calls, behavior):
        _, _, scene = asset(app, base)
        model = importlib.import_module("pyta_platform_backend.schemas.assets")
        created = app.state.asset_service.run(
            "scenarios", scene["id"], 1, model.AssetRunRequest(transport_mode="live")
        )
        root = Path(__file__).resolve().parents[2]
        program = """
import os,sys
from pyta_platform_backend.app import create_app
from pyta_platform_backend.config import BackendSettings
app=create_app(settings=BackendSettings(app_env="test",state_db_path=sys.argv[1]))
repo=app.state.resource_service.repository
original=repo.put_resource
def crash_after_acquire(data):
    result=original(data)
    if data["state"]=="acquired":
        os._exit(23)
    return result
repo.put_resource=crash_after_acquire
app.state.worker_runner.run_next()
"""
        env = dict(
            os.environ,
            PYTHONPATH=str(root / "src") + os.pathsep + str(root / "platform/backend/src"),
        )
        child = subprocess.run(
            [sys.executable, "-c", program, settings.state_db_path],
            env=env,
            cwd=root,
            timeout=10,
            capture_output=True,
            text=True,
        )
        assert child.returncode == 23, child.stderr
        assert len(objects) == 1 and len(calls) == 1
        restarted = importlib.import_module("pyta_platform_backend.app").create_app(
            settings=settings
        )
        with TestClient(restarted) as client:
            assert client.get(f"/api/v1/runs/{created.run_id}").json()["status"] == "interrupted"
            records = client.get(f"/api/v1/runs/{created.run_id}/resources").json()
            assert records[0]["state"] == "needs_reconciliation"
            assert len(calls) == 1  # 重启不能自动重放创建/删除。
            preflight = client.post(f"/api/v1/runs/{created.run_id}/cleanup-preflight").json()
            cleaned = client.post(
                f"/api/v1/runs/{created.run_id}/cleanup",
                json={"preflight_token": preflight["preflight_token"]},
            ).json()
            assert cleaned["results"][0]["state"] == "released"
            assert not objects


@pytest.mark.parametrize("wrong_id", [False, True])
def test_ui_fixture_and_api_readback_release_object_on_assertion_failure(
    platform, monkeypatch, wrong_id
):
    app, _ = platform
    module = importlib.import_module("pyta_platform_backend.runners.journey_worker")

    class Session:
        closed = False

        def act(self, *args):
            pass

        def close(self):
            self.closed = True

    sessions = []

    def factory(version):
        instance = Session()
        sessions.append(instance)
        return instance

    monkeypatch.setattr(module, "WebSession", factory)
    monkeypatch.setattr(module, "capability", lambda *args: {"available": True})
    with server() as (base, objects, calls, behavior):
        target = app.state.context_service.save(
            "targets",
            {"name": "journey lifecycle", "environment_id": "env-demo-mock", "base_url": base},
            creating=True,
        )
        definition = app.state.resource_service.define(
            {
                "name": "UI object",
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
        data = {
            "name": "UI explicit readback",
            "runner_type": "web",
            "target_ref": target["id"],
            "contract_confirmed": True,
            "chromium_version": "test-protocol-only",
            "fixtures": [{"name": "item", "definition_id": definition["id"], "version": 1}],
            "actions": [
                {
                    "step_id": "readback",
                    "name": "readback",
                    "action": "api_assert",
                    "request": {"url": "{{host}}/objects/{{fixtures.item.id}}"},
                    "assertions": [
                        {"name": "object name", "selector": "data.name", "expected": "wrong"}
                        if wrong_id
                        else {"name": "code", "selector": "code", "expected": 200}
                    ],
                }
            ],
        }
        published = app.state.journey_service.define(data)
        created = app.state.journey_service.run(published["id"], 1)
        result = app.state.worker_runner.run_next()
        assert result.status.value == ("failed" if wrong_id else "succeeded"), result.status_message
        assert not objects and result.cleanup_status == "succeeded" and sessions[0].closed
        records = app.state.resource_service.repository.resources(created.run_id)
        assert records[0]["state"] == "released"
        assert result.counts["requests"] == result.counts["assertions"] == 1


def test_ui_resource_plan_rejects_unconfirmed_fixture_before_browser(platform):
    app, _ = platform
    definition = app.state.resource_service.define(
        {
            "name": "unconfirmed UI",
            "strategy": "read_only",
            "pool_id": "unconfirmed",
            "object_id": "object",
        }
    )
    with pytest.raises(Exception) as exc:
        app.state.journey_service.define(
            {
                "name": "unconfirmed",
                "runner_type": "web",
                "target_ref": "default-env-demo-mock",
                "fixtures": [{"name": "item", "definition_id": definition["id"], "version": 1}],
                "actions": [
                    {
                        "step_id": "check",
                        "name": "check",
                        "action": "assert_visible",
                        "selector": {"strategy": "testid", "value": "test"},
                    }
                ],
            }
        )
    assert exc.value.status_code == 400
    assert app.state.run_service.list_runs().total == 0


@pytest.mark.parametrize("runner", ["http", "ui"])
@pytest.mark.parametrize("stop_kind", ["cancel", "timeout"])
def test_stop_between_fixture_acquisitions_prevents_second_create_and_cleans_first(
    platform, monkeypatch, runner, stop_kind
):
    app, _ = platform
    resource_module = importlib.import_module("pyta_platform_backend.workers.resource_plugin")
    original = resource_module.ResourcePlugin.acquire

    def acquire_then_stop(plugin, requirement, scope, context, case):
        value = original(plugin, requirement, scope, context, case)
        if requirement["name"] == "item":
            if stop_kind == "cancel":
                app.state.run_service.cancel_run(context.run_id)
            else:
                context.plugin_state["execution"]["deadline_monotonic"] = 0
        return value

    monkeypatch.setattr(resource_module.ResourcePlugin, "acquire", acquire_then_stop)
    with server() as (base, objects, calls, behavior):
        target, _, scene = asset(app, base, two=True)
        if runner == "http":
            req = importlib.import_module("pyta_platform_backend.schemas.assets").AssetRunRequest(
                transport_mode="live"
            )
            created = app.state.asset_service.run("scenarios", scene["id"], 1, req)
        else:
            ui = importlib.import_module("pyta_platform_backend.runners.journey_worker")
            sessions = []

            class Session:
                closed = False
                calls = []

                def act(self, *args):
                    self.calls.append(args)

                def close(self):
                    self.closed = True

            def start(version):
                session = Session()
                sessions.append(session)
                return session

            monkeypatch.setattr(ui, "WebSession", start)
            monkeypatch.setattr(ui, "capability", lambda *args: {"available": True})
            published = app.state.journey_service.define(
                {
                    "name": "stop during UI data prep",
                    "runner_type": "web",
                    "target_ref": target["id"],
                    "contract_confirmed": True,
                    "chromium_version": "test-protocol-only",
                    "fixtures": scene["draft"]["fixtures"],
                    "actions": [
                        {
                            "step_id": "check",
                            "name": "check",
                            "action": "assert_visible",
                            "selector": {"strategy": "testid", "value": "object"},
                        }
                    ],
                }
            )
            created = app.state.journey_service.run(published["id"], 1)
        result = app.state.worker_runner.run_next()
        assert result.status.value == ("cancelled" if stop_kind == "cancel" else "timed_out")
        assert result.cleanup_status == "succeeded" and not objects
        assert [action for action, obj in calls] == ["create", "delete"]
        rows = app.state.resource_service.repository.resources(created.run_id)
        assert len(rows) == 1 and rows[0]["fixture_id"] == "item" and rows[0]["state"] == "released"
        if runner == "ui":
            assert (
                result.counts["total"] == result.counts["planned"] == result.counts["blocked"] == 1
            )
            assert result.results[0]["status"] == "blocked"
            assert sessions[0].closed and not sessions[0].calls


@pytest.mark.parametrize(
    "snapshots", [{}, {"default": {"target": {"id": "other", "base_url": "http://127.0.0.1:1"}}}]
)
def test_fixture_missing_selected_context_blocks_before_ledger_or_http(platform, snapshots):
    from testflow_engine import ExecutionContext, HttpxTransport, RequestSpec
    from testflow_engine import TestCaseDefinition as Case

    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base)
        model = importlib.import_module("pyta_platform_backend.schemas.assets")
        plan = app.state.asset_service.plan(
            "scenarios", scenario["id"], 1, model.AssetRunRequest(transport_mode="live")
        )
        module = importlib.import_module("pyta_platform_backend.workers.resource_plugin")
        transport = HttpxTransport()
        try:
            plugin = module.ResourcePlugin(
                app.state.resource_service.repository,
                transport,
                snapshots,
                plan["run_definition"]["metadata"]["fixture_plan"],
            )
            context = ExecutionContext(run_id="missing-context", variables={"host": base})
            case = Case(
                case_id="check",
                title="check",
                request=RequestSpec(url=base),
                metadata={"scope_id": "s0", "context_binding_id": "s0"},
            )
            with pytest.raises(module.FixtureBlocked, match="fixture_context_snapshot_missing"):
                plugin.before_case(case, context)
            assert not calls and not objects
            assert app.state.resource_service.repository.resources("missing-context") == []
        finally:
            transport.close()


def test_historical_simulated_resource_cannot_be_cleaned_as_real_http(platform):
    app, _ = platform
    with server() as (base, objects, calls, behavior):
        _, _, scenario = asset(app, base)
        created, detail = run(app, scenario)
        assert detail.status.value == "succeeded"
        repository = app.state.resource_service.repository
        record = repository.resources(created.run_id)[0]
        record.update(simulated=True, state="needs_reconciliation")
        repository.put_resource(record)
        before = list(calls)
        module = importlib.import_module("pyta_platform_backend.workers.resource_plugin")
        with pytest.raises(module.FixtureBlocked, match="historical_simulated_resource_read_only"):
            module.cleanup_record(repository, record)
        assert calls == before
        assert repository.resources(created.run_id)[0]["state"] == "needs_reconciliation"

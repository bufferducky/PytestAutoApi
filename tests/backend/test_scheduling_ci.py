"""R08虚拟时钟/真实CLI：到点、幂等outbox、错过、队列预算与诚实退出。"""

import importlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


@pytest.fixture
def app(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    module = importlib.import_module("pyta_platform_backend.app")
    app = module.create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "schedules.sqlite3")
        )
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code = 500 if self.path == "/500" else 200
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"code": code}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    app.state.test_http_base = f"http://127.0.0.1:{server.server_port}"
    schema = importlib.import_module("pyta_platform_backend.schemas.management")
    env = app.state.management_service.create_environment(
        schema.CreateEnvironmentRequest(
            auth_mode="none", name="scheduler-test", base_url=app.state.test_http_base
        )
    )
    other = app.state.management_service.create_environment(
        schema.CreateEnvironmentRequest(
            auth_mode="none", name="scheduler-other", base_url=app.state.test_http_base
        )
    )
    app.state.test_environment_id = env.id
    app.state.other_environment_id = other.id
    app.state.context_service.save(
        "targets",
        {
            "id": "scheduler-test",
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


def suite(app):
    assets = app.state.asset_service
    model = importlib.import_module("pyta_platform_backend.schemas.assets")
    scene = assets.create(
        "scenarios",
        {
            "name": "scheduled",
            "target_ref": "scheduler-test",
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
    assets.publish(
        "scenarios", scene["id"], model.PublishRequest(expected_revision=1, change_note="schedule")
    )
    suite = assets.create(
        "suites",
        {"name": "scheduled-suite", "scenarios": [{"scenario_id": scene["id"], "version": 1}]},
    )
    assets.publish(
        "suites", suite["id"], model.PublishRequest(expected_revision=1, change_note="pin")
    )
    return suite


def schedule(app, *, missed="skip", busy="queue"):
    service = app.state.schedule_service
    service.clock = lambda: datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
    s = suite(app)
    data = {
        "name": "minute",
        "suite_id": s["id"],
        "suite_version": 1,
        "environment_id": app.state.test_environment_id,
        "transport_mode": "live",
        "cron": "* * * * *",
        "status": "active",
        "missed_policy": missed,
        "busy_policy": busy,
    }
    return service.save(data)


def test_not_due_no_trigger_repeated_scan_once_and_fixed_version(app):
    service = app.state.schedule_service
    plan = schedule(app)
    before = datetime(2026, 10, 25, 0, 0, 59, tzinfo=timezone.utc)
    assert service.tick(before) == []
    due = before + timedelta(seconds=1)
    first = service.tick(due)
    second = service.tick(due)
    assert len(first) == 1 and second == []
    assert len(service.repository.triggers(plan["id"])) == 1
    detail = app.state.worker_runner.run_next()
    assert detail.status.value == "succeeded" and detail.transport_mode == "live"
    assert detail.payload["asset_ref"]["version"] == 1
    assert detail.eligible_for_release


@pytest.mark.parametrize(
    ("policy", "run_count", "missed_count"), [("skip", 0, 3), ("fire_once", 1, 2)]
)
def test_downtime_three_occurrences_skip_or_fire_once(app, policy, run_count, missed_count):
    plan = schedule(app, missed=policy)
    service = app.state.schedule_service
    now = datetime(2026, 10, 25, 0, 3, tzinfo=timezone.utc)
    service.tick(now, recovering=True)
    triggers = service.repository.triggers(plan["id"])
    assert sum(row["state"] == "missed" for row in triggers) == missed_count
    assert app.state.run_service.list_runs().total == run_count
    service.tick(now, recovering=True)
    assert app.state.run_service.list_runs().total == run_count


def test_outbox_recovery_after_run_creation_is_idempotent(app, monkeypatch):
    service = app.state.schedule_service
    plan = schedule(app)
    now = datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc)

    def crash(data):
        raise RuntimeError("crash after create run")

    with monkeypatch.context() as patch:
        patch.setattr(service.repository, "set_trigger", crash)
        with pytest.raises(RuntimeError):
            service.tick(now)
    assert app.state.run_service.list_runs().total == 1
    assert service.repository.triggers(plan["id"])[0]["state"] == "pending"
    service.tick(now)
    assert app.state.run_service.list_runs().total == 1
    assert service.repository.triggers(plan["id"])[0]["state"] == "queued"
    # 重复提示不能重复认领已完成任务。
    assert app.state.worker_runner.run_next().status.value == "succeeded"
    assert app.state.worker_runner.run_next() is None


def test_cron_timezone_weekday_preview_and_cas_pause(app):
    service = app.state.schedule_service
    plan = schedule(app)
    public = {
        key: value
        for key, value in plan.items()
        if key not in {"id", "revision", "next_fire_at", "migration_required"}
    }
    updated = service.save({**public, "cron": "0 9 * * 1-5"}, plan["id"], plan["revision"])
    preview = service.preview(plan["id"])
    assert preview["times"][0] == "2026-10-26T09:00:00+08:00"
    assert len(preview["times"]) == 5
    with pytest.raises(Exception) as exc:
        service.save(public, plan["id"], plan["revision"])
    assert exc.value.status_code == 409
    service.change_status(plan["id"], updated["revision"], "paused")
    assert service.tick(datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc)) == []
    assert service.get(plan["id"])["status"] == "paused"
    assert not any(row.get("migration_required") for row in service.repository.schedules())


def test_busy_skip_and_queue_wait_expiry_without_request(app):
    service = app.state.schedule_service
    plan = schedule(app, busy="skip")
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    own = app.state.run_service.create_run(
        schema.CreateRunRequest(
            suite_id="busy",
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
    )
    claimed = app.state.run_service.repository.claim(own.run_id)
    service.tick(datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc))
    assert service.repository.triggers(plan["id"])[0]["state"] == "busy_skipped"
    app.state.run_service.repository.finish(
        own.run_id, claimed.attempt_id, schema.RunStatus.ERROR, "injected"
    )
    public = {
        key: value
        for key, value in plan.items()
        if key not in {"id", "revision", "next_fire_at", "migration_required"}
    }
    service.save(
        {**public, "busy_policy": "queue", "queue_timeout_seconds": 1}, plan["id"], plan["revision"]
    )
    service.tick(datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc))
    queued = app.state.run_service.repository.list_queued_records()[0]
    repo = app.state.run_service.repository
    with repo._transaction():
        old = repo.get_by_id(queued.run_id)
        old.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        repo._connection.execute(
            "UPDATE runs SET created_at=? WHERE run_id=?", (old.created_at.isoformat(), old.run_id)
        )
    result = app.state.worker_runner.run_next()
    if result is None:  # 内存投递器可能还保留已终止任务的提示。
        result = app.state.worker_runner.run_next()
    assert result.status.value == "timed_out" and result.results == []


def test_release_report_never_claims_missing_company_contracts_are_passed(app):
    schedule(app)
    app.state.schedule_service.tick(datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc))
    detail = app.state.worker_runner.run_next()
    report = app.state.release_service.build(
        {"run_ids": [detail.run_id], "mode": "strict", "build": "test-build"}
    )
    assert not report["eligible_for_release"] and report["exit_code"] != 0
    assert all("S" + str(i).zfill(2) in report["unverified_risks"] for i in range(1, 17))
    informational = app.state.release_service.build({"run_ids": [detail.run_id]})
    assert (
        informational["mode"] == "report_only"
        and informational["decision"] == "report_only_no_deployment_approval"
    )


def test_default_notifications_disabled_and_authorized_local_sender_deduplicates(app):
    service = app.state.notification_service
    messages = []
    assert (
        service.notify("local", "failed", {"message": "failure"})["reason"]
        == "disabled_or_not_authorized"
    )
    with pytest.raises(ValueError):
        service.register_authorized_sender("local", messages.append)
    service.register_authorized_sender("local", messages.append, authorized=True)
    assert service.notify("local", "failed", {"message": "failure"})["sent"]
    assert not service.notify("local", "failed", {"message": "failure"})["sent"]
    assert service.notify("local", "succeeded", {"message": "recovered"})["sent"]
    assert not service.notify("local", "succeeded", {"message": "recovered"})["sent"]
    assert len(messages) == 2

    def fail(message):
        raise RuntimeError("local delivery failure")

    service.register_authorized_sender("broken", fail, authorized=True)
    for _ in range(3):
        assert service.notify("broken", "failed", {})["pending"]
    assert service.notify("broken", "failed", {})["reason"] == "delivery_retry_limit"


@contextmanager
def cli_server():
    cancellations = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            key = self.path.split("/")[-1]
            status = {
                "pass": "succeeded",
                "fail": "failed",
                "error": "error",
                "blocked": "blocked",
                "mock": "succeeded",
                "queued": "queued",
            }[key]
            body = {"run_id": key, "status": status, "eligible_for_release": key == "pass"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_POST(self):
            cancellations.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1", cancellations
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cli_subprocess_exit_codes_and_timeout_cancellation():
    root = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ, PYTHONPATH=str(root / "src") + os.pathsep + str(root / "platform/backend/src")
    )
    with cli_server() as (url, cancellations):
        for key, expected in [("pass", 0), ("fail", 1), ("error", 2), ("blocked", 3), ("mock", 3)]:
            result = subprocess.run(
                [sys.executable, "-m", "pyta_platform_backend.cli", "--base-url", url, "get", key],
                env=env,
                cwd=root,
                timeout=10,
                capture_output=True,
                text=True,
            )
            assert result.returncode == expected, result.stderr
            assert json.loads(result.stdout)["run_id"] == key
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pyta_platform_backend.cli",
                "--base-url",
                url,
                "wait",
                "queued",
                "--timeout",
                "0.05",
            ],
            env=env,
            cwd=root,
            timeout=10,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2 and "/api/v1/runs/queued/cancel" in cancellations
        assert json.loads(result.stdout)["run_id"] == "queued"


def test_scheduler_service_survives_app_recreation_backup_and_invalid_cron(app):
    service = app.state.schedule_service
    created = schedule(app)
    service.tick(datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc))
    module = importlib.import_module("pyta_platform_backend.app")
    restarted = module.create_app(settings=app.state.settings)
    assert (
        restarted.state.schedule_service.get(created["id"])["next_fire_at"]
        == "2026-10-25T00:02:00+00:00"
    )
    trigger = restarted.state.schedule_service.repository.triggers(created["id"])[0]
    assert restarted.state.run_service.get_run_detail(trigger["run_id"]).status.value == "queued"
    status = restarted.state.schedule_service.status()
    assert not status["worker_available"] and status["database_integrity"] == "ok"
    assert status["latest_backup"] is None
    data = {
        key: value
        for key, value in created.items()
        if key not in {"id", "revision", "next_fire_at", "migration_required"}
    }
    for invalid in ["* * *", "61 * * * *", "* * * * 9"]:
        with pytest.raises(Exception) as exc:
            service.save({**data, "cron": invalid})
        assert exc.value.status_code == 400
    assert (
        restarted.state.schedule_service.repository.triggers(created["id"])[0]["id"]
        == trigger["id"]
    )


def test_pause_pending_outbox_prevents_dispatch_and_queue_create_idempotency(app):
    service = app.state.schedule_service
    plan = schedule(app)
    payload = service._plan(plan)
    trigger = service.repository.trigger(plan, "2026-10-25T00:01:00+00:00", "pending", payload)
    service.change_status(plan["id"], plan["revision"], "paused")
    assert service._deliver(trigger)["state"] == "cancelled_before_dispatch"
    assert app.state.run_service.list_runs().total == 0


def test_http_schedule_crud_preview_release_and_default_no_notification(app):
    from fastapi.testclient import TestClient

    plan = schedule(app)
    # 创建时已active，但应用启动恢复采用skip，不会补跑公司请求。
    with TestClient(app) as client:
        assert client.get("/api/v1/schedule-plans").status_code == 200
        assert len(client.get(f"/api/v1/schedules/{plan['id']}/preview").json()["times"]) == 5
        assert client.get("/api/v1/scheduler/status").json()["worker_available"]
        response = client.post(
            f"/api/v1/schedules/{plan['id']}/pause", json={"expected_revision": plan["revision"]}
        )
        assert response.status_code == 200
        assert (
            client.post(
                f"/api/v1/schedules/{plan['id']}/resume",
                json={"expected_revision": plan["revision"]},
            ).status_code
            == 409
        )
        assert not app.state.notification_service.channels


def notification_run(app, code, environment_id=None):
    environment_id = environment_id or app.state.test_environment_id
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    return app.state.run_service.create_run(
        schema.CreateRunRequest(
            suite_id="notification-stream",
            environment_id=environment_id,
            payload={
                "execution_mode": "standard_run",
                "transport_mode": "live",
                "run_definition": {
                    "cases": [
                        {
                            "case_id": "check",
                            "title": "check",
                            "request": {"url": app.state.test_http_base + "/" + str(code)},
                            "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                        }
                    ]
                },
            },
        )
    )


def test_actual_background_worker_invokes_opt_in_local_notification_and_deduplicates(app):
    import time
    from threading import Event

    messages = []
    arrived = Event()

    def local_sender(message):
        messages.append(message)
        arrived.set()

    app.state.notification_service.register_authorized_sender(
        "local-only", local_sender, authorized=True
    )
    app.state.worker_host.start()

    def wait_run(identifier):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            detail = app.state.run_service.get_run_detail(identifier)
            if detail.status.value not in {"queued", "running"}:
                return detail
            Event().wait(0.01)
        raise AssertionError("worker did not finish")

    try:
        failed = notification_run(app, 500)
        assert arrived.wait(3)
        assert wait_run(failed.run_id).status.value == "failed"
        arrived.clear()
        repeated = notification_run(app, 500)
        assert wait_run(repeated.run_id).status.value == "failed"
        recovered = notification_run(app, 200)
        assert arrived.wait(3)
        assert wait_run(recovered.run_id).status.value == "succeeded"
        assert [message["state"] for message in messages] == ["failed", "succeeded"]
        assert [message["summary"]["run_id"] for message in messages] == [
            failed.run_id,
            recovered.run_id,
        ]
        assert all(message["summary"]["validation_scope"] == "live" for message in messages)
    finally:
        app.state.worker_host.stop()


def test_run_notification_state_is_separate_for_environment_and_default_has_no_sender(app):
    service = app.state.notification_service
    messages = []
    first = notification_run(app, 500)
    one = app.state.worker_runner.run_next()
    assert service.notify_finished(one) == []
    assert not service.channels
    service.register_authorized_sender("local-only", messages.append, authorized=True)
    service.notify_finished(one)
    notification_run(app, 200, app.state.other_environment_id)
    two = app.state.worker_runner.run_next()
    assert service.notify_finished(two)[0]["reason"] == "healthy_unchanged"
    recovered = notification_run(app, 200)
    three = app.state.worker_runner.run_next()
    assert service.notify_finished(three)[0]["sent"]
    assert len(messages) == 2 and messages[-1]["summary"]["run_id"] == recovered.run_id
    assert messages[0]["summary"]["run_id"] == first.run_id


def test_notification_sender_failure_does_not_change_run_and_retries_are_bounded(app):
    service = app.state.notification_service
    attempts = []

    def broken(message):
        attempts.append(message)
        raise RuntimeError("controlled local sender failure")

    service.register_authorized_sender("broken-local", broken, authorized=True)
    for _ in range(4):
        created = notification_run(app, 500)
        detail = app.state.worker_runner.run_next()
        outcome = service.notify_finished(detail)[0]
        assert not outcome["sent"] and outcome["pending"]
        stored = app.state.run_service.get_run_detail(created.run_id)
        assert stored.status.value == "failed" and stored.results == detail.results
    assert len(attempts) == 3
    assert outcome["reason"] == "delivery_retry_limit"


def test_worker_notification_failure_is_visible_without_changing_business_result(app):
    import time
    from threading import Event

    entered = Event()

    def broken(message):
        entered.set()
        raise RuntimeError("controlled delivery failure")

    app.state.notification_service.register_authorized_sender(
        "broken-local", broken, authorized=True
    )
    app.state.worker_host.start()
    try:
        created = notification_run(app, 500)
        assert entered.wait(3)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not app.state.worker_host.notification_error:
            Event().wait(0.01)
        assert (
            app.state.schedule_service.status()["notification_error"]
            == "notification_delivery_pending"
        )
        deliveries = app.state.schedule_service.repository.notification_deliveries()
        assert (
            len(deliveries) == 1
            and deliveries[0]["delivered"] is False
            and deliveries[0]["attempts"] == 1
        )
        assert app.state.run_service.get_run_detail(created.run_id).status.value == "failed"
    finally:
        app.state.worker_host.stop()

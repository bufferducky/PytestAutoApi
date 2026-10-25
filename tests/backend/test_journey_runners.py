"""R09机制验证；受控session替身不是浏览器/真机业务验收。"""

import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest
from test_support import seed_test_environments


@pytest.fixture
def app(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    app = importlib.import_module("pyta_platform_backend.app").create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "ui.sqlite3")
        )
    )

    return seed_test_environments(app)


def journey(**changes):
    return {
        "name": "local UI protocol example",
        "runner_type": "web",
        "target_ref": "default-env-demo-mock",
        "chromium_version": "controlled-test-version",
        "contract_confirmed": True,
        "synthetic_test_data": True,
        "actions": [
            {"step_id": "open", "name": "open", "action": "navigate", "path": "/"},
            {
                "step_id": "check",
                "name": "check",
                "action": "assert_text",
                "selector": {"strategy": "testid", "value": "result"},
                "value": "expected",
            },
        ],
        **changes,
    }


def test_missing_driver_and_unconfirmed_contract_create_blocked_run_without_network(
    app, monkeypatch
):
    module = importlib.import_module("pyta_platform_backend.runners.ui")
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None)
    for runner in ["web", "android"]:
        data = journey(runner_type=runner, contract_confirmed=False)
        if runner == "android":
            data["actions"][1]["selector"] = {"strategy": "accessibility_id", "value": "result"}
        created = app.state.journey_service.define(data)
        pre = app.state.journey_service.preflight(created["id"], 1)
        assert not pre["available"] and pre["blocked_reasons"]
        run = app.state.journey_service.run(created["id"], 1)
        result = app.state.worker_runner.run_next()
        assert result.run_id == run.run_id and result.status.value == "blocked"
        assert not result.eligible_for_release and result.counts["executed"] == 0


@pytest.mark.parametrize("strategy", ["css", "xpath", "coordinate"])
def test_fragile_or_arbitrary_selectors_rejected(app, strategy):
    data = journey()
    data["actions"][1]["selector"]["strategy"] = strategy
    with pytest.raises(Exception) as exc:
        app.state.journey_service.define(data)
    assert exc.value.status_code == 400


class ControlledSession:
    def __init__(self, fail=False):
        self.calls = []
        self.closed = False
        self.fail = fail

    def act(self, action, value, base):
        self.calls.append((action["step_id"], value))
        if self.fail and action["action"].startswith("assert_"):
            raise AssertionError("expected mismatch")

    def screenshot(self):
        return b"controlled synthetic screenshot"

    def close(self):
        self.closed = True


def test_controlled_session_contract_success_failure_cancel_and_permission_restore(app):
    module = importlib.import_module("pyta_platform_backend.runners.ui")
    data = (
        importlib.import_module("pyta_platform_backend.schemas.journeys")
        .JourneyDefinition(**journey())
        .model_dump()
    )
    data["_base_url"] = "https://example.test"
    session = ControlledSession()
    status, cleanup, results = module.execute_journey(data, session, {})
    assert status == "succeeded" and cleanup == "succeeded" and session.closed and len(results) == 2
    session = ControlledSession(fail=True)
    artifacts = []
    status, cleanup, results = module.execute_journey(
        data, session, {}, artifact=lambda step, content: artifacts.append(step)
    )
    assert status == "failed" and session.closed and artifacts == ["check"]
    session = ControlledSession()
    status, cleanup, results = module.execute_journey(data, session, {}, stop=lambda: True)
    assert status == "cancelled" and session.closed and not session.calls
    action = {
        "step_id": "permission",
        "name": "permission",
        "action": "permission",
        "timeout_seconds": 1,
        "permission": "android.permission.RECORD_AUDIO",
        "permission_granted": False,
        "restore_permission_granted": True,
    }
    permissions = (
        importlib.import_module("pyta_platform_backend.schemas.journeys")
        .JourneyDefinition(**journey(runner_type="android", actions=[action]))
        .model_dump()
    )
    permissions["_base_url"] = "https://example.test"
    session = ControlledSession()
    module.execute_journey(permissions, session, {})
    assert len(session.calls) == 2 and session.closed


def test_worker_adapter_records_controlled_protocol_evidence_not_real_device(app, monkeypatch):
    module = importlib.import_module("pyta_platform_backend.runners.journey_worker")
    sessions = []

    def factory(version):
        session = ControlledSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(module, "WebSession", factory)
    monkeypatch.setattr(module, "capability", lambda *args: {"available": True})
    created = app.state.journey_service.define(journey())
    run = app.state.journey_service.run(created["id"], 1)
    result = app.state.worker_runner.run_next()
    assert result.run_id == run.run_id
    assert result.status.value == "succeeded" and len(result.results) == 2
    assert result.results[0]["metadata"]["runner_type"] == "web" and sessions[0].closed
    # 单测是受控适配器协议，不写成真实公司Web/Android通过证据。
    assert app.state.journey_service.readiness()["risks"][0]["validation"] == "unverified"


def test_quarantine_retains_reason_expiry_and_unverified_coverage(app):
    created = app.state.journey_service.define(journey(risk_id="W01"))
    expires = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    saved = app.state.journey_service.quarantine(
        created["id"], 1, "selector requires stable ID", expires
    )
    assert saved["data"]["expires_at"] == expires
    readiness = app.state.journey_service.readiness()
    assert len(readiness["risks"]) == 8 and readiness["quarantines"]
    assert all(risk["validation"] == "unverified" for risk in readiness["risks"])


def test_device_profile_requires_secret_ref_exact_build_and_local_appium(app):
    data = {
        "name": "device",
        "device_secret_ref": "env:PYTA_SECRET_ANDROID_DEVICE",
        "platform_version": "14",
        "app_build_sha256": "a" * 64,
        "installed_build_version": "1.0.22",
        "media_capabilities": ["playback"],
    }
    saved = app.state.journey_service.device(data)
    assert saved["data"]["device_secret_ref"].startswith("env:")
    for change in [
        {"device_secret_ref": "actual-serial"},
        {"app_build_sha256": "unknown"},
        {"appium_url": "https://arbitrary.test"},
    ]:
        with pytest.raises(Exception) as exc:
            app.state.journey_service.device({**data, **change})
        assert exc.value.status_code == 400


def test_worker_persists_first_action_before_next_action_and_cancel_accounts_for_plan(
    app, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    module = importlib.import_module("pyta_platform_backend.runners.journey_worker")
    entered, release = Event(), Event()
    sessions = []

    class Slow(ControlledSession):
        def act(self, action, value, base):
            super().act(action, value, base)
            if action["step_id"] == "check":
                entered.set()
                assert release.wait(3)

    def factory(version):
        session = Slow()
        sessions.append(session)
        return session

    monkeypatch.setattr(module, "WebSession", factory)
    monkeypatch.setattr(module, "capability", lambda *args: {"available": True})
    data = journey()
    data["actions"].append(
        {
            "step_id": "later",
            "name": "later",
            "action": "click",
            "selector": {"strategy": "testid", "value": "later"},
        }
    )
    published = app.state.journey_service.define(data)
    created = app.state.journey_service.run(published["id"], 1)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(app.state.worker_runner.run_next)
        try:
            assert entered.wait(3)
            mid = app.state.run_service.get_run_detail(created.run_id)
            assert mid.status.value == "running" and [row["case_id"] for row in mid.results] == [
                "open"
            ]
            assert mid.counts["assertions"] == 0  # navigate不能被伪装成有效断言。
            app.state.run_service.cancel_run(created.run_id)
        finally:
            release.set()
        result = future.result(timeout=3)
    assert (
        result.status.value == "cancelled"
        and result.counts["total"] == result.counts["planned"] == 3
    )
    assert result.counts["executed"] == 2 and result.counts["blocked"] == 1
    assert [name for name, value in sessions[0].calls] == ["open", "check"] and sessions[0].closed


def test_total_budget_is_timeout_not_assertion_failure_and_writes_evidence(app, monkeypatch):
    module = importlib.import_module("pyta_platform_backend.runners.ui")
    model = importlib.import_module("pyta_platform_backend.schemas.journeys").JourneyDefinition
    data = model(**journey()).model_dump()
    data["_base_url"] = "https://example.test"
    times = iter([0, 2, 2])
    monkeypatch.setattr(module, "monotonic", lambda: next(times))
    recorded = []
    session = ControlledSession()
    status, cleanup, results = module.execute_journey(
        data, session, {}, deadline=1, on_result=recorded.append
    )
    assert status == "timed_out" and cleanup == "succeeded" and session.closed
    assert results[0].status.value == "timed_out" and results[1].status.value == "blocked"
    assert recorded == results


def test_result_storage_error_stops_ui_actions_and_still_closes_session(app):
    module = importlib.import_module("pyta_platform_backend.runners.ui")
    model = importlib.import_module("pyta_platform_backend.schemas.journeys").JourneyDefinition
    data = model(**journey()).model_dump()
    data["_base_url"] = "https://example.test"
    session = ControlledSession()

    def fail(case):
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        module.execute_journey(data, session, {}, on_result=fail)
    assert session.closed and [name for name, value in session.calls] == ["open"]


def test_ui_expected_value_ref_records_resolved_business_value(app):
    module = importlib.import_module("pyta_platform_backend.runners.ui")
    model = importlib.import_module("pyta_platform_backend.schemas.journeys").JourneyDefinition
    data = model(
        **journey(
            actions=[
                {
                    "step_id": "check",
                    "name": "same object",
                    "action": "assert_text",
                    "selector": {"strategy": "testid", "value": "object"},
                    "value_ref": "fixtures.item.id",
                }
            ]
        )
    ).model_dump()
    data["_base_url"] = "https://example.test"
    session = ControlledSession()
    status, cleanup, results = module.execute_journey(
        data, session, {"fixtures": {"item": {"id": "run-owned-object"}}}
    )
    assert status == "succeeded"
    assert session.calls == [("check", "run-owned-object")]
    assert results[0].steps[0].assertions[0].expected == "run-owned-object"


@pytest.mark.parametrize("capture", ["capture_trace", "capture_video"])
def test_native_capture_requires_explicit_synthetic_data(app, capture):
    with pytest.raises(Exception) as exc:
        app.state.journey_service.define(journey(**{capture: True, "synthetic_test_data": False}))
    assert exc.value.status_code == 400
    assert app.state.run_service.list_runs().total == 0


def test_native_capture_refuses_configured_credential_identity(app):
    identity = app.state.context_service.save(
        "identity-profiles",
        {
            "name": "test-only identity",
            "target_ids": ["default-env-demo-mock"],
            "username_secret_ref": "env:PYTA_SECRET_TEST_USER",
            "password_secret_ref": "env:PYTA_SECRET_TEST_PASSWORD",
        },
        creating=True,
    )
    with pytest.raises(Exception) as exc:
        app.state.journey_service.define(journey(capture_trace=True, identity_ref=identity["id"]))
    assert exc.value.status_code == 400

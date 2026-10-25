"""证据驱动门禁：测试仅证明规则，不把临时样例记成公司的业务验收。"""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from test_support import seed_test_environments


@pytest.fixture
def app(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    app = importlib.import_module("pyta_platform_backend.app").create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "evidence.sqlite3")
        )
    )

    return seed_test_environments(app)


def controlled_web_evidence(app, monkeypatch):
    worker = importlib.import_module("pyta_platform_backend.runners.journey_worker")

    class Session:
        def act(self, *args):
            pass

        def close(self):
            pass

    monkeypatch.setattr(worker, "capability", lambda *args: {"available": True})
    monkeypatch.setattr(worker, "WebSession", lambda version: Session())
    published = app.state.journey_service.define(
        {
            "name": "controlled W01 rule proof",
            "runner_type": "web",
            "risk_id": "W01",
            "target_ref": "default-env-demo-mock",
            "contract_confirmed": True,
            "chromium_version": "controlled-only",
            "actions": [
                {
                    "step_id": "visible",
                    "name": "visible",
                    "action": "assert_visible",
                    "selector": {"strategy": "testid", "value": "example"},
                }
            ],
        }
    )
    created = app.state.journey_service.run(published["id"], 1, build="build-test")
    result = app.state.worker_runner.run_next()
    assert result.run_id == created.run_id and result.status.value == "succeeded"
    return published, result


def test_ui_readiness_uses_fresh_same_scope_versioned_evidence_and_not_permanent_flags(
    app, monkeypatch
):
    published, result = controlled_web_evidence(app, monkeypatch)
    service = app.state.journey_service
    readiness = service.readiness(
        environment_id="env-demo-mock", build="build-test", run_ids=[result.run_id]
    )
    first = readiness["risks"][0]
    assert first["risk_id"] == "W01" and first["validation"] == "verified"
    assert first["latest_evidence"]["run_id"] == result.run_id
    assert all(row["validation"] == "unverified" for row in readiness["risks"][1:])
    for scope in [
        {"environment_id": "env-default-live"},
        {"build": "wrong-build"},
        {"run_ids": []},
    ]:
        assert service.readiness(**scope)["risks"][0]["validation"] == "unverified"
    report = app.state.release_service.build(
        {"run_ids": [result.run_id], "mode": "strict", "build": "build-test"}
    )
    assert "W01" not in report["unverified_risks"] and "A01" in report["unverified_risks"]
    assert not report["eligible_for_release"]  # 其他公司风险仍然缺证据，不能借一条UI样例放行。
    updated = service.define({"id": published["id"], **published["data"], "name": "new version"})
    assert updated["version"] == 2
    assert service.readiness()["risks"][0]["validation"] == "unverified"


def test_quarantine_needs_resolution_even_after_expiry_and_keeps_history(app, monkeypatch):
    published, result = controlled_web_evidence(app, monkeypatch)
    service = app.state.journey_service
    q = service.quarantine(
        published["id"],
        1,
        "controlled selector failure",
        (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    assert service.readiness()["risks"][0]["validation"] == "unverified"
    # 把临时记录设为已到期，验证“到期需处理”而不是自动解除风险。
    with service.repository.transaction():
        data = service.repository.version("quarantine", q["id"], 1)
        data["data"]["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        from pyta_platform_backend.repositories.asset_repository import asset_hash

        data["hash"] = asset_hash(data["data"])
        import json

        service.repository._connection.execute(
            "UPDATE asset_versions SET data_json=? WHERE kind=? AND id=?",
            (json.dumps(data), "quarantine", q["id"]),
        )
    assert service.readiness()["risks"][0]["validation"] == "unverified"
    resolution = service.resolve_quarantine(q["id"], "controlled fix and fresh evidence checked")
    ready = service.readiness()
    assert ready["risks"][0]["validation"] == "verified"
    assert ready["quarantines"] and ready["quarantine_resolutions"][0]["id"] == resolution["id"]


def test_ui_stale_and_pruned_evidence_cannot_refresh_release(app, monkeypatch):
    published, result = controlled_web_evidence(app, monkeypatch)
    repository = app.state.run_service.repository
    with repository._transaction():
        record = repository.get_by_id(result.run_id)
        record.finished_at = datetime.now(timezone.utc) - timedelta(days=8)
        repository._save(record)
    assert app.state.journey_service.readiness()["risks"][0]["validation"] == "unverified"
    with repository._transaction():
        record = repository.get_by_id(result.run_id)
        record.finished_at = datetime.now(timezone.utc)
        record.execution["evidence_pruned_at"] = datetime.now(timezone.utc).isoformat()
        repository._save(record)
    assert app.state.journey_service.readiness()["risks"][0]["validation"] == "unverified"


def test_core_risk_mapping_requires_explicit_valid_id_and_cannot_disable_required_gate(app):
    assets = app.state.asset_service
    row = assets.repository.save_coverage(
        {
            "id": "controlled",
            "system": "saas",
            "risk": "controlled risk",
            "contract_status": "unconfirmed",
            "scenario_refs": [],
            "contract_note": None,
        }
    )
    mapped = assets.update_coverage(
        row["id"], 1, {"regression_id": "S01", "required_for_release": False}
    )
    assert mapped["required_for_release"] is True
    assert assets.coverage_summary()["required_unverified"] == ["controlled"]
    with pytest.raises(Exception) as exc:
        assets.update_coverage(row["id"], mapped["revision"], {"regression_id": "S99"})
    assert exc.value.status_code == 400


def test_strict_gate_checks_required_scope_not_all_static_observations(app, monkeypatch):
    # 本地HTTP真值+隔离的UI门禁替身，只验证聚合算法正路径，不冒充Android或公司业务。
    from test_wait_integration import async_service

    with async_service(["done"]) as (base, calls):
        target = app.state.context_service.save(
            "targets",
            {
                "name": "local aggregation proof",
                "environment_id": "env-demo-mock",
                "base_url": base,
            },
            creating=True,
        )
        service = app.state.asset_service
        scene = service.create(
            "scenarios",
            {
                "name": "controlled required risk evidence",
                "target_ref": target["id"],
                "steps": [
                    {
                        "step_id": "read",
                        "name": "read",
                        "contract_confirmed": True,
                        "request": {"url": "{{host}}/status"},
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    }
                ],
            },
        )
        model = importlib.import_module("pyta_platform_backend.schemas.assets")
        service.publish(
            "scenarios",
            scene["id"],
            model.PublishRequest(expected_revision=1, change_note="controlled proof"),
        )
        created = service.run(
            "scenarios",
            scene["id"],
            1,
            model.AssetRunRequest(
                transport_mode="live", environment_id="env-demo-mock", build="build-test"
            ),
        )
        assert app.state.worker_runner.run_next().status.value == "succeeded"
        for index in range(1, 17):
            service.repository.save_coverage(
                {
                    "id": f"core-{index}",
                    "regression_id": f"S{index:02d}",
                    "required_for_release": True,
                    "contract_status": "confirmed",
                    "contract_note": "controlled aggregation fixture, not company acceptance",
                    "scenario_refs": [{"scenario_id": scene["id"], "version": 1}],
                }
            )
        service.repository.save_coverage(
            {"id": "static-unconfirmed", "contract_status": "unconfirmed", "scenario_refs": []}
        )
        monkeypatch.setattr(
            app.state.release_service,
            "journeys",
            SimpleNamespace(
                readiness=lambda **kwargs: {
                    "risks": [
                        {"risk_id": f"{prefix}{i:02d}", "validation": "verified"}
                        for prefix in ["W", "A"]
                        for i in range(1, 5)
                    ]
                }
            ),
        )
        report = app.state.release_service.build(
            {"run_ids": [created.run_id], "mode": "strict", "build": "build-test"}
        )
        assert report["eligible_for_release"] and report["exit_code"] == 0
        assert report["unverified_risks"] == []
        assert report["unverified_discovered_observations"] == ["static-unconfirmed"]
        wrong = app.state.release_service.build(
            {"run_ids": [created.run_id], "mode": "strict", "build": "wrong-build"}
        )
        assert not wrong["eligible_for_release"] and "S01" in wrong["unverified_risks"]

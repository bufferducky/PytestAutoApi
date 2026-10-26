"""未保存草稿的真实 HTTP 调试、前置隔离与正式证据边界。"""

import asyncio
import importlib
from copy import deepcopy

import httpx
import pytest
from fastapi import HTTPException
from test_scenario_assets import draft, publish, request
from test_scenario_assets import platform as asset_platform


@pytest.fixture
def debug_platform(tmp_path):
    yield from asset_platform.__wrapped__(tmp_path)


def debug_request(data, **extra):
    model = importlib.import_module("pyta_platform_backend.schemas.assets").DraftDebugRequest
    return model(draft=data, live_confirmed=True, **extra)


def query_draft():
    data = draft()
    data["steps"] = [data["steps"][1]]
    data["steps"][0]["depends_on"] = []
    data["steps"][0]["request"]["url"] = "{{host}}/query"
    return data


def test_unsaved_debug_executes_current_content_without_publishing(debug_platform):
    app, settings = debug_platform
    service = app.state.asset_service
    original = query_draft()
    asset = service.create("scenarios", original)
    editing = deepcopy(original)
    editing["name"] = "unsaved edit"
    editing["steps"][0]["assertions"][0]["expected"] = "changed expectation"
    before = app.state.run_service.repository.live_stats()
    run = service.debug(debug_request(editing, asset_id=asset["id"], revision=asset["revision"]))
    editing["name"] = "edited again after submission"
    result = app.state.worker_runner.run_next()
    assert result.run_id == run.run_id
    assert result.status.value == "failed", result.results
    assert result.counts["requests"] == 1
    assert not result.eligible_for_release
    assert result.validation_scope == "debug"
    assert result.payload["debug_snapshot"]["draft"]["name"] == "unsaved edit"
    assert service.get("scenarios", asset["id"])["draft"] == asset["draft"]
    assert service.repository.versions("scenarios", asset["id"]) == []
    assert app.state.run_service.repository.live_stats() == before
    restored = importlib.import_module("pyta_platform_backend.app").create_app(settings=settings)
    persisted = restored.state.run_service.get_run_detail(run.run_id)
    assert persisted.payload["debug_snapshot"] == result.payload["debug_snapshot"]
    assert persisted.validation_scope == "debug"


def test_debug_success_cannot_be_release_evidence_or_formal_stats(debug_platform):
    app, _ = debug_platform
    service = app.state.asset_service
    service.debug(debug_request(query_draft(), build="build-1"))
    result = app.state.worker_runner.run_next()
    assert result.status.value == "succeeded", result.results
    assert result.counts["assertions"] > 0
    assert not result.eligible_for_release
    assert "asset_ref" not in result.payload
    assert "scenario_refs" not in result.payload
    assert all("scenario_ref" not in r.get("metadata", {}) for r in result.results)
    assert app.state.run_service.repository.live_stats()["total"] == 0
    exit_code = importlib.import_module("pyta_platform_backend.services.release_service").exit_code
    assert exit_code(result) == 3
    # A later formal version is unaffected by the debug record.
    asset = service.create("scenarios", query_draft())
    publish(app, asset)
    service.run("scenarios", asset["id"], 1, request(build="build-1"))
    formal = app.state.worker_runner.run_next()
    assert formal.eligible_for_release
    assert app.state.run_service.repository.live_stats()["total"] == 1


def test_single_step_requires_inputs_and_never_executes_producer(debug_platform):
    app, _ = debug_platform
    service = app.state.asset_service
    data = draft()
    with pytest.raises(HTTPException) as caught:
        service.debug(debug_request(data, step_id="verify"))
    assert caught.value.status_code == 400
    assert caught.value.detail["missing_inputs"] == ["outputs.create.id"]
    assert app.state.run_service.repository.list_runs(100, 0).total == 0
    run = service.debug(debug_request(data, step_id="verify", inputs={"create": {"id": "manual"}}))
    result = app.state.worker_runner.run_next()
    assert result.run_id == run.run_id
    assert result.status.value == "succeeded", result.results
    assert [r["case_id"] for r in result.results] == ["s0__verify"]
    assert result.counts["requests"] == 1
    assert result.payload["side_effects"] == [
        {"scenario_id": "unsaved-draft", "step_id": "verify", "kind": "query"}
    ]


def test_full_debug_preserves_setup_and_cleanup(debug_platform):
    app, _ = debug_platform
    app.state.asset_service.debug(debug_request(draft()))
    result = app.state.worker_runner.run_next()
    assert result.status.value == "succeeded", result.results
    assert result.cleanup_status == "succeeded"
    assert [r["case_id"] for r in result.results] == ["s0__create", "s0__verify", "s0__cleanup"]


def test_single_step_checks_custom_rule_inputs_before_queueing(debug_platform, monkeypatch):
    from testflow_engine.assertions.business import CUSTOM_RULES

    app, _ = debug_platform
    service = app.state.asset_service
    monkeypatch.setitem(
        CUSTOM_RULES,
        "draft-debug@1",
        (lambda actual, expected, inputs: True, ("outputs.create.id",)),
    )
    data = draft()
    data["steps"][1]["request"]["url"] = "{{host}}/query"
    data["steps"][1]["assertions"][0]["rule_ref"] = "draft-debug@1"
    with pytest.raises(HTTPException) as caught:
        service.debug(debug_request(data, step_id="verify"))
    assert caught.value.detail["missing_inputs"] == ["outputs.create.id"]
    assert app.state.run_service.repository.list_runs(100, 0).total == 0
    service.debug(debug_request(data, step_id="verify", inputs={"create": {"id": "manual"}}))
    result = app.state.worker_runner.run_next()
    assert result.status.value == "succeeded", result.results
    assert result.counts["requests"] == 1
    assert [r["case_id"] for r in result.results] == ["s0__verify"]


def test_debug_rejects_unconfirmed_contract_and_resource_bypass(debug_platform):
    app, _ = debug_platform
    service = app.state.asset_service
    data = query_draft()
    data["steps"][0]["contract_confirmed"] = False
    with pytest.raises(HTTPException, match=""):
        service.debug(debug_request(data))
    with pytest.raises(HTTPException) as caught:
        service.debug(debug_request(draft(), step_id="create"))
    assert "整场景" in str(caught.value.detail)
    assert app.state.run_service.repository.list_runs(100, 0).total == 0


def test_debug_pending_cancellation_and_rerun_keep_debug_purpose(debug_platform):
    app, _ = debug_platform
    service = app.state.asset_service
    run = service.debug(debug_request(query_draft()))
    cancelled = app.state.run_service.cancel_run(run.run_id)
    assert cancelled.status.value == "cancelled"
    assert cancelled.validation_scope == "debug"
    rerun = app.state.run_service.rerun(run.run_id)
    assert app.state.run_service.get_run_detail(rerun.run_id).payload["run_purpose"] == "debug"
    assert app.state.run_service.repository.live_stats()["total"] == 0


def test_debug_cancelled_queue_does_not_resume_after_restart(debug_platform):
    app, settings = debug_platform
    run = app.state.asset_service.debug(debug_request(query_draft()))
    app.state.run_service.cancel_run(run.run_id)
    restored = importlib.import_module("pyta_platform_backend.app").create_app(settings=settings)
    assert restored.state.worker_runner.run_next() is None
    detail = restored.state.run_service.get_run_detail(run.run_id)
    assert detail.status.value == "cancelled"
    assert detail.validation_scope == "debug"
    assert detail.results == []


def test_debug_route_requires_explicit_confirmation_and_queues_only(debug_platform):
    app, _ = debug_platform

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            invalid = await client.post("/api/v1/scenarios/debug", json={"draft": query_draft()})
            assert invalid.status_code == 422
            for field, value in (
                ("context_snapshots", {"default": {}}),
                ("run_definition", {"cases": []}),
                ("run_purpose", "formal"),
            ):
                bypass = await client.post(
                    "/api/v1/scenarios/debug",
                    json={"draft": query_draft(), "live_confirmed": True, field: value},
                )
                assert bypass.status_code == 422
            assert app.state.run_service.repository.list_runs(100, 0).total == 0
            accepted = await client.post(
                "/api/v1/scenarios/debug",
                json={
                    "draft": query_draft(),
                    "live_confirmed": True,
                },
            )
            assert accepted.status_code == 202, accepted.text
            detail = app.state.run_service.get_run_detail(accepted.json()["run_id"])
            assert detail.status.value == "queued"
            assert detail.results == []

    asyncio.run(scenario())

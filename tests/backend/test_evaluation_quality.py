"""历史评估读取、禁用新执行与确定性指标；不调用模型。"""

import importlib
import sys

import pytest


@pytest.fixture
def app(tmp_path):
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    return importlib.import_module("pyta_platform_backend.app").create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "evaluation.sqlite3")
        )
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"provider_ref": "local-replay@1", "local_outputs": {"sample": {"text": "ok"}}},
        {"provider_ref": "authorized@1", "budget": {"max_calls": 100}},
    ],
)
def test_new_evaluation_is_disabled_before_any_lookup_or_call(app, payload):
    service = app.state.evaluation_service
    calls = []
    service.register_provider("authorized@1", calls.append, authorized_paid_calls=True)
    before = app.state.run_service.list_runs().total
    with pytest.raises(Exception) as exc:
        service.run(payload)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "evaluation_execution_disabled"
    assert not calls
    assert app.state.run_service.list_runs().total == before


def historical_report(app, suffix="", dataset_hash="dataset-hash"):
    """Load historical evidence directly; never use a product execution endpoint."""
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    repo = app.state.run_service.repository
    record = repo.create_pending_run(
        schema.CreateRunRequest(
            suite_id="historical-evaluation" + suffix,
            payload={"execution_mode": "evaluation", "transport_mode": "mock"},
        )
    )
    claimed = repo.claim(record.run_id)
    repo.finish(
        record.run_id,
        claimed.attempt_id,
        schema.RunStatus.SUCCEEDED,
        "historical simulated evaluation",
        cleanup_status="succeeded",
    )
    app.state.evaluation_service.save_report(
        record.run_id,
        {
            "run_id": record.run_id,
            "dataset_hash": dataset_hash,
            "rubric_hash": "rubric-hash",
            "task": "text",
            "repeats": 1,
            "quality_gate": "not_calibrated_not_approved",
            "provider_ref": "local-replay@1",
            "calls": 1,
            "results": [{"sample_id": "sample", "quality": {"status": "passed"}}],
            "mode": "report_only",
            "unassessed": [],
        },
    )
    return record.run_id


def test_historical_report_reads_without_relabeling_simulation(app):
    run_id = historical_report(app)
    report = app.state.evaluation_service.report(run_id)
    detail = app.state.run_service.get_run_detail(run_id)
    assert report["provider_ref"] == "local-replay@1"
    assert detail.transport_mode == "mock" and not detail.eligible_for_release
    assert report["human_calibration"]["independently_reviewed_samples"] == 0
    with pytest.raises(Exception) as exc:
        app.state.run_service.rerun(run_id)
    assert exc.value.status_code == 409
    assert "evaluation_execution_disabled" in exc.value.detail


def test_historical_reviews_remain_append_only_and_fixture_not_human(app):
    run_id = historical_report(app)
    service = app.state.evaluation_service
    data = {
        "decision": "failed",
        "reviewer": "automated-test",
        "reason": "historical test fixture",
        "review_source": "test_fixture",
    }
    first = service.review(run_id, "sample", data)
    second = service.review(run_id, "sample", data)
    assert first["id"] != second["id"]
    report = service.report(run_id)
    assert len(report["human_reviews"]) == 2
    assert report["results"][0]["quality"]["status"] == "passed"
    assert report["human_calibration"]["independently_reviewed_samples"] == 0
    assert set(report["review_conflicts"]) == {first["id"], second["id"]}


@pytest.mark.parametrize("field", ["id", "run_id", "sample_id", "created_at"])
def test_review_cannot_override_historical_ownership(app, field):
    run_id = historical_report(app)
    with pytest.raises(Exception) as exc:
        app.state.evaluation_service.review(
            run_id,
            "sample",
            {
                "decision": "passed",
                "reviewer": "automated-test",
                "reason": "fixture review",
                "review_source": "test_fixture",
                field: "forged",
            },
        )
    assert exc.value.status_code == 400


def test_historical_report_comparison_keeps_version_boundaries(app):
    service = app.state.evaluation_service
    first = historical_report(app, "first")
    second = historical_report(app, "second")
    different = historical_report(app, "different", "other-dataset")
    assert service.compare(first, second)["same_dataset_rubric"]
    with pytest.raises(Exception) as exc:
        service.compare(first, different)
    assert exc.value.status_code == 400


def test_seed_local_disabled_and_normal_dataset_validation_stays(app):
    service = app.state.evaluation_service
    with pytest.raises(Exception) as exc:
        service.seed()
    assert exc.value.status_code == 410
    with pytest.raises(Exception) as exc:
        service.dataset({"name": "invalid", "samples": []})
    assert exc.value.status_code == 400


def test_actual_asgi_rejects_execution_but_reads_historical_report(app):
    from fastapi.testclient import TestClient

    run_id = historical_report(app)
    with TestClient(app) as client:
        response = client.post("/api/v1/evaluation-runs", json={})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "evaluation_execution_disabled"
        assert client.get(f"/api/v1/evaluation-runs/{run_id}").json()["run_id"] == run_id
        assert client.post("/api/v1/evaluation-datasets/seed-local").status_code == 410


def test_worker_evaluation_entry_never_calls_provider(app):
    module = importlib.import_module("pyta_platform_backend.runners.evaluation")
    with pytest.raises(ValueError, match="evaluation_execution_disabled"):
        module.run_evaluation(None, None, None, None)


def test_text_rules_do_not_claim_full_hallucination_detection():
    module = importlib.import_module("pyta_platform_backend.runners.evaluation")
    sample = {
        "required_concepts": [["预算", "费用上限"], ["预约", "预定"]],
        "forbidden_concepts": ["保证治愈"],
    }
    assert (
        module.quality(sample, {"text": "费用上限已明确，可以预定时间。"}, "text")["status"]
        == "passed"
    )
    assert module.quality(sample, {"text": "预算已明确。"}, "text")["status"] == "failed"
    assert module.quality(sample, {"text": "预算、预约，保证治愈。"}, "text")["status"] == "failed"
    assert module.quality(sample, {"text": ""}, "text")["status"] == "failed"
    assert (
        "不是完整幻觉检测" in module.quality(sample, {"text": "预算和预约"}, "text")["limitations"]
    )


def test_asr_character_error_entities_and_tts_format_are_deterministic(tmp_path):
    import io
    import wave

    module = importlib.import_module("pyta_platform_backend.runners.evaluation")
    metrics = module.asr_metrics("预算一百元", "预算二百元", ["一百元"])
    assert (
        metrics["character_error_rate"] == pytest.approx(1 / 5) and metrics["entity_accuracy"] == 0
    )
    assert module.asr_metrics("你好 世界", "你好世界")["character_error_rate"] == 0
    with pytest.raises(ValueError):
        module.asr_metrics("", "not golden")
    assert not module.tts_metrics(b"")["valid"]
    content = io.BytesIO()
    with wave.open(content, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    assert module.tts_metrics(content.getvalue())["duration_seconds"] == pytest.approx(0.1)
    assert module.tts_metrics(content.getvalue())["human_listening"] == "not_reviewed"

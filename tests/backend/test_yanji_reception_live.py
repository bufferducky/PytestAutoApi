"""显式启用的言迹只读验收；平台资产只写隔离的本地验证库。"""

import importlib
import json
import os

import pytest
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    os.environ.get("PYTA_RUN_YANJI_RECEPTION_LIVE") != "1",
    reason="显式启用的言迹测试API与只读MySQL验收",
)


def test_yanji_reception_pack_published_suite_twice():
    url = os.environ.get("PLATFORM_BACKEND_DATABASE_URL", "")
    assert url and (make_url(url).database or "").startswith("pyta_validation"), (
        "真实验收只能将平台资产写入pyta_validation前缀的隔离库"
    )
    from fastapi.testclient import TestClient
    from pyta_platform_backend.config import BackendSettings
    from pyta_platform_backend.schemas.assets import PublishRequest

    app = importlib.import_module("pyta_platform_backend.app").create_app(
        BackendSettings.from_env()
    )
    client = TestClient(app)
    payload = {
        "target_ref": os.environ.get("PYTA_YANJI_TARGET_REF", "yanji-reception-test"),
        "identity_ref": os.environ.get("PYTA_YANJI_IDENTITY_REF", "yanji-reception-automation"),
        "binding_ref": os.environ.get("PYTA_YANJI_BINDING_REF", "yanji-reception-project"),
        "expected_user_id": os.environ["PYTA_YANJI_EXPECTED_USER_ID"],
        "datasource_ref": os.environ.get("PYTA_YANJI_DATASOURCE_REF", "yanji-test"),
    }
    check = client.post(
        f"/api/v1/business-datasources/{payload['datasource_ref']}/preflight",
        json={**payload, "execute_query": True},
    )
    assert check.status_code == 200, check.json()
    assert check.json() == {
        "configuration": "passed",
        "connection": "passed",
        "permission": "passed",
        "errors": [],
    }
    imported = client.post("/api/v1/imports/yanji-reception", json=payload)
    assert imported.status_code == 201, imported.json()
    assert imported.json()["network_executed"] is False
    assets = imported.json()["assets"]
    assert len(assets) == 11
    references = []
    for asset in assets:
        identifier = asset["id"]
        checked = client.post(f"/api/v1/scenarios/{identifier}/preflight")
        assert checked.status_code == 200 and checked.json()["valid"], checked.json()
        versions = client.get(f"/api/v1/scenarios/{identifier}/versions").json()
        if not versions:
            app.state.asset_service.publish(
                "scenarios",
                identifier,
                PublishRequest(
                    expected_revision=asset["revision"],
                    change_note="言迹测试接诊筛选只读验收",
                ),
            )
            versions = client.get(f"/api/v1/scenarios/{identifier}/versions").json()
        references.append({"scenario_id": identifier, "version": versions[0]["version"]})

    # 每次验收创建自己的固定版本套件，不覆盖已有草稿或借用其他运行的绿色。
    suite = app.state.asset_service.create(
        "suites",
        {"name": "言迹接诊筛选 · 真实只读验收", "scenarios": references,
         "priority": "P0", "timeout_seconds": 600},
    )
    app.state.asset_service.publish(
        "suites",
        suite["id"],
        PublishRequest(expected_revision=suite["revision"], change_note="固定11条接诊场景版本"),
    )
    summaries = []
    failures = []
    for round_number in (1, 2):
        queued = client.post(
            f"/api/v1/suites/{suite['id']}/versions/1/runs",
            json={"transport_mode": "live", "build": "unspecified"},
        )
        assert queued.status_code == 202, queued.json()
        run_id = queued.json()["run_id"]
        result = app.state.worker_runner.run_next()
        assert result is not None and result.run_id == run_id
        summary = {
            "round": round_number,
            "run_id": run_id,
            "suite_id": suite["id"],
            "status": result.status.value,
            "counts": result.counts,
            "failed_steps": [
                {"case_id": item["case_id"], "title": item["title"],
                 "status": item["status"], "error": item.get("error"),
                 "differences": [assertion["actual"] for step in item.get("steps", [])
                                 for assertion in step.get("assertions", [])
                                 if assertion.get("name") == "数据库接诊集合与分页"
                                 and assertion.get("status") != "passed"]}
                for item in result.results if item["status"] not in {"passed", "skipped"}
            ],
        }
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False))
        # 检查公开run/结果没有登录口令、DB口令或认证值。
        detail = client.get(f"/api/v1/runs/{run_id}").json()
        serialized = json.dumps(detail, ensure_ascii=False)
        for key in ("PYTA_SECRET_YANJI_DB_PASSWORD", "PYTA_SECRET_YANJI_TEST_PASSWORD"):
            secret = os.environ.get(key)
            assert not secret or secret not in serialized
        if result.status.value != "succeeded":
            failures.append(run_id)
    output = os.environ.get("PYTA_YANJI_VALIDATION_SUMMARY")
    if output:
        from pathlib import Path

        Path(output).write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n")
    assert not failures, f"真实回归保留失败记录: {failures}"

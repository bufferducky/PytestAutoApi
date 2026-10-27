"""Validate deployed source and optional Chromium as the image's default user."""

import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from pyta_platform_backend.app import create_app
from pyta_platform_backend.config import BackendSettings
from pyta_platform_backend.integrations.yanji.query_pack import query_drafts
from pyta_platform_backend.repositories import SqliteRunRepository, SqlRunRepository
from pyta_platform_backend.repositories.serialization import dump_json
from pyta_platform_backend.repositories.sqlite_support import dump_json as old_dump_json
from pyta_platform_backend.services.yanji_regression import query_drafts as old_query_drafts
from pyta_platform_backend.workers.run_worker import RunWorker
from pyta_platform_backend.workers.runner import MemoryWorkerRunner

assert os.getuid() == 10001
assert MemoryWorkerRunner is RunWorker
assert SqlRunRepository is SqliteRunRepository
assert dump_json is old_dump_json
assert query_drafts is old_query_drafts
bundle = files("pyta_platform_backend.integrations.yanji.data")
hashes = {
    name: hashlib.sha256(bundle.joinpath(name).read_bytes()).hexdigest()
    for name in ["yanji-contracts.json", "yanji-research.json"]
}
assert not Path("/app/src/testflow_engine/business_data").exists()
app = create_app(
    settings=BackendSettings(
        app_env="test",
        state_db_path="/tmp/release-check.sqlite3",
        artifact_root="/tmp/release-check-artifacts",
    )
)
with TestClient(app) as client:
    response = client.get("/api/v1/regression-packs/yanji")
    assert response.status_code == 200
    assert len(response.json()["contracts"]) == 16
    assert client.get("/api/v1/demo-suites").json()["items"] == []
    assert client.post("/api/v1/demo-suites/retired/runs", json={"mode": "live"}).status_code == 410
    report = app.state.asset_service.import_research()
    assert sum(row["observations"] for row in report["sources"].values()) == 650
    assert app.state.run_service.list_runs().total == 0
with sync_playwright() as runtime:
    browser = runtime.chromium.launch(headless=True)
    version = browser.version
    browser.close()
print(
    json.dumps(
        {
            "uid": os.getuid(),
            "bundles": hashes,
            "contracts": 16,
            "research_observations": 650,
            "chromium_version": version,
            "business_requests_executed": False,
        }
    )
)

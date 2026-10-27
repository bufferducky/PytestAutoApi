"""在仅复制发布源码的目录验证模块导入和业务资料交付。"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_release_layout_loads_yanji_bundles_and_compatibility_imports(tmp_path):
    root = Path(__file__).resolve().parents[2]
    release = tmp_path / "release"
    # 对齐 Docker 的两个源码 COPY，不提供 docs、Files 或原始业务资料目录。
    for source in ("src", "platform/backend/src"):
        shutil.copytree(
            root / source,
            release / source,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    script = '''
import json
from pathlib import Path
from fastapi.testclient import TestClient
from pyta_platform_backend.app import create_app
from pyta_platform_backend.config import BackendSettings
from pyta_platform_backend.integrations.yanji.query_pack import query_drafts
from pyta_platform_backend.repositories import (
    SqlRunRepository, SqlManagementRepository, SqliteRunRepository, SqliteManagementRepository,
)
from pyta_platform_backend.repositories.serialization import dump_json
from pyta_platform_backend.repositories.sqlite_support import dump_json as old_dump_json
from pyta_platform_backend.services.yanji_regression import query_drafts as old_query_drafts
from pyta_platform_backend.workers.run_worker import RunWorker
from pyta_platform_backend.workers.runner import MemoryWorkerRunner
import testflow_engine
import pyta_platform_backend

release = Path.cwd()
assert Path(testflow_engine.__file__).is_relative_to(release)
assert Path(pyta_platform_backend.__file__).is_relative_to(release)
assert SqlRunRepository is SqliteRunRepository
assert SqlManagementRepository is SqliteManagementRepository
assert MemoryWorkerRunner is RunWorker
assert dump_json is old_dump_json
assert query_drafts is old_query_drafts
settings = BackendSettings(
    app_env="test", state_db_path=str(release / "state.sqlite3"),
    artifact_root=str(release / "artifacts"),
)
assert settings.resolve_database_url() == settings.resolve_state_db_path()
app = create_app(settings=settings)
with TestClient(app) as client:
    response = client.get("/api/v1/regression-packs/yanji")
    assert response.status_code == 200, response.text
    contracts = response.json()
    assert contracts["schema_version"] == 1
    assert {row["regression_id"] for row in contracts["contracts"]} == {
        "S" + str(i).zfill(2) for i in range(1, 17)
    }
    imported = app.state.asset_service.import_research()
    assert {key: value["observations"] for key, value in imported["sources"].items()} == {
        "center": 213, "saas": 346, "app": 91,
    }
    assert app.state.run_service.list_runs().total == 0
print(json.dumps({"contracts": len(contracts["contracts"]), "network_executed": False}))
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=release,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                str(release / path) for path in ("src", "platform/backend/src")
            ),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

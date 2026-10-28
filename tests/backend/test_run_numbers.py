"""运行展示编号不承担关联主键职责，重试/重启/回滚都不能改变已分配编号。"""

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pyta_platform_backend.repositories.run_repository import (
    InMemoryRunRepository,
    SqlRunRepository,
)
from pyta_platform_backend.schemas.run import CreateRunRequest


def request(name="言迹接诊筛选 · 只读验收"):
    return CreateRunRequest(
        suite_id="opaque-asset-id",
        payload={"run_definition": {"name": name}},
    )


@pytest.mark.parametrize("persistent", [False, True])
def test_number_unique_monotonic_idempotent_and_name_snapshot(tmp_path, persistent):
    path = tmp_path / "state.sqlite3"
    repo = SqlRunRepository(path) if persistent else InMemoryRunRepository()
    first = repo.create_pending_run(request(), idempotency_key="once")
    retry = repo.create_pending_run(request(), idempotency_key="once")
    assert (retry.run_id, retry.run_number) == (first.run_id, first.run_number)
    other = SqlRunRepository(path) if persistent else repo
    with ThreadPoolExecutor(4) as pool:
        records = list(
            pool.map(lambda i: (repo if i % 2 else other).create_pending_run(request()), range(12))
        )
    numbers = [record.run_number for record in records]
    assert len(set(numbers)) == 12
    assert min(numbers) > first.run_number
    detail = other.get_detail(first.run_id)
    assert detail.run_number == str(first.run_number)
    assert detail.name == "言迹接诊筛选 · 只读验收"
    assert detail.suite_id == "opaque-asset-id"
    assert len(first.run_id) == 32
    listed = other.list_runs(limit=20, offset=0)
    assert all(item.name == detail.name for item in listed.items)


def test_number_and_outbox_rollback_together(tmp_path, monkeypatch):
    repo = SqlRunRepository(tmp_path / "rollback.sqlite3")
    original = repo._connection.upsert

    def fail_outbox(table, *args, **kwargs):
        if table == "run_outbox":
            raise RuntimeError("outbox unavailable")
        return original(table, *args, **kwargs)

    monkeypatch.setattr(repo._connection, "upsert", fail_outbox)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        repo.create_pending_run(request())
    for table in ("runs", "run_numbers", "run_outbox"):
        assert repo._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_create_list_detail_share_number_and_snapshot_name():
    from pyta_platform_backend.services.run_service import RunService
    from pyta_platform_backend.workers.dispatcher import MemoryRunDispatcher

    service = RunService(InMemoryRunRepository(), MemoryRunDispatcher())
    payload = request()
    payload.payload.update(execution_mode="standard_run", transport_mode="live")
    payload.payload["run_definition"]["cases"] = [
        {
            "case_id": "query",
            "title": "只登记不执行",
            "request": {"url": "http://127.0.0.1/not-executed"},
            "assertions": [{"name": "code", "selector": "code", "expected": 200}],
        }
    ]
    response = service.create_run(payload)
    assert response.run_number == "1"
    payload.payload["run_definition"]["name"] = "后续修改不影响已创建快照"
    detail = service.get_run_detail(response.run_id)
    summary = service.list_runs().items[0]
    assert detail.run_number == summary.run_number == response.run_number
    assert detail.name == summary.name == "言迹接诊筛选 · 只读验收"


def test_migration_backfills_by_creation_time_and_is_repeatable(tmp_path):
    repo = SqlRunRepository(tmp_path / "migration.sqlite3")
    first = repo.create_pending_run(request())
    second = repo.create_pending_run(request())
    store = repo._connection
    store.execute("DROP TABLE run_numbers")
    path = Path(__file__).parents[2] / "platform/backend/alembic/versions/0002_run_numbers.py"
    spec = importlib.util.spec_from_file_location("run_numbers_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with store.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
    assert repo.get_detail(first.run_id).run_number == "1"
    assert repo.get_detail(second.run_id).run_number == "2"
    assert repo.create_pending_run(request()).run_number == 3

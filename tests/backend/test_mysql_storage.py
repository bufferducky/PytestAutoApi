"""真实 MySQL 验证；独立 pyta_validation 库，禁止对业务数据库清理。"""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import make_url


@pytest.fixture
def mysql_store():
    url = os.environ.get("PYTA_TEST_MYSQL_URL")
    if not url:
        pytest.skip("设置 PYTA_TEST_MYSQL_URL 运行真实 MySQL 集成测试")
    if not make_url(url).database.startswith("pyta_validation"):
        pytest.fail("集成测试仅允许 pyta_validation 前缀的独立库")
    from pyta_platform_backend.db.schema import metadata
    from pyta_platform_backend.db.store import Store

    store = Store(url)
    with store.engine.begin() as connection:
        for table in reversed(metadata.sorted_tables):
            if table.name != "write_guard":
                connection.execute(delete(table))
    return url, store


def request():
    from pyta_platform_backend.schemas.run import CreateRunRequest

    return CreateRunRequest(
        suite_id="mysql-suite",
        payload={
            "execution_mode": "standard_run",
            "transport_mode": "live",
            "run_definition": {
                "cases": [
                    {
                        "case_id": "read",
                        "title": "read",
                        "request": {"url": "http://127.0.0.1/not-executed"},
                        "assertions": [{"name": "code", "selector": "code", "expected": 200}],
                    }
                ]
            },
        },
    )


def test_mysql_large_run_payload_list_does_not_filesort_json(mysql_store):
    from pyta_platform_backend.repositories.run_repository import SqlRunRepository

    url, _ = mysql_store
    repo = SqlRunRepository(url)
    created = []
    for _ in range(4):
        payload = request()
        payload.payload["public_note"] = "large-regression-plan-" * 16000
        created.append(repo.create_pending_run(payload).run_id)
    with repo._transaction():
        original = repo._connection.execute("SELECT @@SESSION.sort_buffer_size").fetchone()[0]
        try:
            repo._connection.execute("SET SESSION sort_buffer_size=32768")
            listed = repo.list_runs(limit=4, offset=0)
            assert [item.run_id for item in listed.items] == list(reversed(created))
        finally:
            repo._connection.execute("SET SESSION sort_buffer_size=?", (original,))


def test_mysql_atomic_outbox_claim_and_recovery(mysql_store):
    from pyta_platform_backend.repositories.run_repository import RunConflict, SqlRunRepository
    from pyta_platform_backend.workers.dispatcher import PersistentRunDispatcher

    url, store = mysql_store
    repo = SqlRunRepository(url)
    run = repo.create_pending_run(request())
    assert (
        store.execute("SELECT state FROM run_outbox WHERE run_id=?", (run.run_id,)).fetchone()[0]
        == "pending"
    )
    # 第二连接模拟重启后的消费者，不依赖内存中的 dispatch 提示。
    other = SqlRunRepository(url)
    dispatcher = PersistentRunDispatcher(other)
    assert dispatcher.pull_next().run_id == run.run_id
    assert dispatcher.pull_next() is None

    def claim(repository):
        try:
            return repository.claim(run.run_id).attempt_id
        except RunConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(claim, [repo, other]))
    assert sum(x is not None for x in claims) == 1
    other.recover_interrupted()
    detail = repo.get_detail(run.run_id)
    assert detail.status.value == "interrupted"
    assert not detail.eligible_for_release
    assert (
        store.execute("SELECT state FROM run_outbox WHERE run_id=?", (run.run_id,)).fetchone()[0]
        == "done"
    )


def test_mysql_failed_transaction_leaves_no_run_or_outbox(mysql_store, monkeypatch):
    from pyta_platform_backend.repositories.run_repository import SqlRunRepository

    url, store = mysql_store
    repo = SqlRunRepository(url)
    original = repo._connection.upsert

    def fail(table, *args, **kwargs):
        if table == "run_outbox":
            raise RuntimeError("outbox write failed")
        return original(table, *args, **kwargs)

    monkeypatch.setattr(repo._connection, "upsert", fail)
    with pytest.raises(RuntimeError, match="outbox"):
        repo.create_pending_run(request())
    assert store.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert store.execute("SELECT COUNT(*) FROM run_outbox").fetchone()[0] == 0


def test_mysql_real_catalog_versions_and_context(mysql_store):
    from pyta_platform_backend.repositories.asset_repository import AssetRepository
    from pyta_platform_backend.repositories.context_repository import ContextRepository
    from pyta_platform_backend.repositories.management_repository import SqlManagementRepository

    url, _ = mysql_store
    management = SqlManagementRepository(url)
    assert management.list_cases() == []
    assert management.list_environments() == []
    env = management.create_environment(
        name="真实测试环境",
        base_url="http://127.0.0.1",
        auth_mode="none",
        status="draft",
        variables={"a": 1},
    )
    assert SqlManagementRepository(url).get_environment_by_id(env.id).variables == {"a": 1}
    assets = AssetRepository(url)
    draft = {"name": "用户信息", "module": "用户", "steps": [], "priority": "P1"}
    assets.create("scenarios", draft, "scenario-real")
    version = assets.publish("scenarios", "scenario-real", 1, draft, "初始版本", "owner")
    assert version["version"] == 1
    assert management.list_cases()[0].status == "active"
    assets.create(
        "suites",
        {"name": "真实套件", "scenarios": [{"scenario_id": "scenario-real", "version": 1}]},
        "suite-real",
    )
    assert management.list_suites()[0].case_count == 1
    contexts = ContextRepository(url)
    contexts.save("targets", {"id": "target-real", "name": "test"}, creating=True)
    assert ContextRepository(url).get("targets", "target-real")["revision"] == 1


def test_mysql_resource_schedule_and_artifacts(mysql_store, tmp_path):
    from pyta_platform_backend.repositories.artifact_repository import ArtifactRepository
    from pyta_platform_backend.repositories.resource_repository import ResourceRepository
    from pyta_platform_backend.repositories.schedule_repository import ScheduleRepository

    url, _ = mysql_store
    resources = ResourceRepository(url)
    item = {"id": "resource", "run_id": "run", "state": "acquired"}
    resources.put_resource(item)
    resources.put_resource({**item, "state": "released"})
    assert resources.resources("run")[0]["state"] == "released"
    schedules = ScheduleRepository(url)
    plan = schedules.save_schedule({"id": "plan", "status": "active"})
    first = schedules.trigger(plan, "2026-10-25T00:00:00+00:00", "pending", {})
    second = schedules.trigger(plan, "2026-10-25T00:00:00+00:00", "pending", {})
    assert first["id"] == second["id"]
    assert len(schedules.triggers()) == 1
    schedules.save_notification("channel", {"pending": True})
    schedules.save_notification("channel", {"pending": False})
    assert schedules.notification("channel") == {"pending": False}
    artifacts = ArtifactRepository(url, tmp_path)
    meta = artifacts.add("run", "step", b"real bytes", "text/plain", "redacted", 14)
    assert ArtifactRepository(url, tmp_path).content(meta) == b"real bytes"


def test_mysql_live_stats_excludes_imported_history(mysql_store):
    from pyta_platform_backend.repositories.run_repository import SqlRunRepository

    url, _ = mysql_store
    repo = SqlRunRepository(url)
    repo.create_pending_run(request())
    historical = repo.create_pending_run(request())
    with repo._transaction():
        historical.execution["migration"] = {"source": "historical_demo", "do_not_resume": True}
        repo._save(historical)
    assert repo.live_stats() == {"total": 1, "queued": 1, "running": 0, "failed": 0}
    assert len(repo.list_queued_records()) == 1


def test_mysql_worker_singleton_lock(mysql_store):
    from pyta_platform_backend.repositories.run_repository import SqlRunRepository
    from pyta_platform_backend.workers.host import WorkerHost

    class Idle:
        def run_next(self):
            return None

    url, _ = mysql_store
    first = WorkerHost(Idle(), SqlRunRepository(url), url)
    second = WorkerHost(Idle(), SqlRunRepository(url), url)
    first.start()
    try:
        with pytest.raises(RuntimeError, match="已有 worker"):
            second.start()
    finally:
        first.stop()
    assert not first.available


def test_mysql_app_executes_real_http_and_reads_after_recreation(mysql_store):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from pyta_platform_backend.app import create_app
    from pyta_platform_backend.config import BackendSettings
    from pyta_platform_backend.schemas.run import CreateRunRequest

    url, _ = mysql_store
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"code": 200}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings = BackendSettings(app_env="test", database_url=url)
        app = create_app(settings=settings)
        data = request().payload
        data["run_definition"]["cases"][0]["request"]["url"] = (
            f"http://127.0.0.1:{server.server_port}/real-request"
        )
        run = app.state.run_service.create_run(CreateRunRequest(suite_id="real", payload=data))
        result = app.state.worker_runner.run_by_id(run.run_id)
        assert result.status.value == "succeeded"
        assert result.transport_mode == "live"
        assert result.counts["requests"] == 1
        assert received == ["/real-request"]
        recreated = create_app(settings=settings)
        persisted = recreated.state.run_service.get_run_detail(run.run_id)
        assert persisted.status.value == "succeeded"
        assert persisted.results[0]["case_id"] == "read"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_worker_lock_supports_maximum_mysql_database_name(tmp_path, monkeypatch):
    """Exercise MySQL lock naming without connecting to the shared test server."""
    from types import SimpleNamespace

    from pyta_platform_backend.db import store
    from pyta_platform_backend.repositories.run_repository import SqlRunRepository
    from pyta_platform_backend.workers.host import WorkerHost

    names = []

    class Connection:
        engine = SimpleNamespace(url=SimpleNamespace(database="d" * 64))

        def execute(self, statement, parameters):
            name = parameters["name"]
            assert len(name) <= 64
            names.append(name)
            return SimpleNamespace(scalar=lambda: 1)

        def close(self):
            pass

    # Build the offline repository before replacing its engine factory.
    repository = SqlRunRepository(str(tmp_path / "worker.sqlite3"))
    monkeypatch.setattr(store, "engine_for", lambda _: SimpleNamespace(connect=Connection))
    host = WorkerHost(SimpleNamespace(run_next=lambda: None), repository, "mysql+pymysql://test")
    host.start()
    host.stop()
    assert names
    assert len(set(names)) == 1
    assert not host.available

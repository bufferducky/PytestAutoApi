"""业务只读核验的故障注入：真实执行器、受控数据库边界与版本编译。"""

import importlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from testflow_engine import ResponseSnapshot
from testflow_engine import TestFlowEngine as FlowEngine
from testflow_engine.executor.transport import TransportAdapter


def modules():
    return tuple(
        importlib.import_module("pyta_platform_backend." + name)
        for name in (
            "services.business_datasources",
            "integrations.yanji.reception_oracle",
            "workers.business_database_plugin",
            "integrations.yanji.reception_pack",
            "services.scenario_compiler",
        )
    )


@pytest.fixture
def configured(monkeypatch):
    # 旧骨架测试会加载fake FastAPI；本组ASGI与worker必须使用真实装配模块。
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    sources, _, _, _, _ = modules()
    config = {
        "id": "yanji-test",
        "host": "127.0.0.1",
        "port": 3306,
        "schema": "yanji",
        "tenant_id": "11",
        "project_id": "22",
        "username_secret_ref": "env:PYTA_SECRET_DB_USER",
        "password_secret_ref": "env:PYTA_SECRET_DB_PASSWORD",
    }
    monkeypatch.setenv("PYTA_BUSINESS_DATASOURCES_JSON", json.dumps([config]))
    monkeypatch.setenv("PYTA_SECRET_DB_USER", "db-user-sentinel")
    monkeypatch.setenv("PYTA_SECRET_DB_PASSWORD", "db-pass-sentinel")
    snapshot = {
        "target": {"base_url": "https://api-test.yanjiai.com"},
        "identity": {"id": "test-user"},
        "binding": {"tenant_id": "11", "project_id": "22"},
    }
    return sources.resolve_source("yanji-test", snapshot), snapshot


def facts():
    start = datetime(2026, 9, 21, 10)
    return [
        {
            "id": str(index),
            "tenant_id": "11",
            "dept_id": "22",
            "reception_user": "42",
            "reception_time": start + timedelta(minutes=index),
            "create_time": start + timedelta(seconds=index // 2),
            "status": 5,
            "customer_type": "新客户",
            "record_count": 1,
            "record_seconds": 120 if index % 2 else 119,
            "keyword_hit": 1,
        }
        for index in range(1, 9)
    ]


def test_config_secrets_missing_drift_and_scope(configured, monkeypatch):
    sources, _, _, _, _ = modules()
    source, snapshot = configured
    assert sources.public_sources()[0]["configuration"] == "passed"
    assert "db-pass-sentinel" not in json.dumps(sources.public_sources())
    with pytest.raises(sources.BusinessDataError, match="context_mismatch"):
        sources.resolve_source(source["id"], {**snapshot, "binding": {"project_id": "other"}})
    monkeypatch.delenv("PYTA_SECRET_DB_PASSWORD")
    assert sources.preflight_source(source["id"], snapshot, "7")["configuration"] == "failed"
    monkeypatch.setenv("PYTA_BUSINESS_DATASOURCES_JSON", '{"bad":1}')
    with pytest.raises(sources.BusinessDataError, match="configuration_invalid"):
        sources.registry()


def test_date_duration_and_multiselect_rules():
    _, oracle, _, _, _ = modules()
    rows = facts()
    assert len(oracle.expected_rows(rows, {"recordDurationStatus": 2})) == 4
    assert len(oracle.expected_rows(rows, {"recordDurationStatus": 1})) == 4
    rows[0]["record_count"] = 0
    rows[0]["record_seconds"] = 0
    assert [row["id"] for row in oracle.expected_rows(rows, {"recordDurationStatus": 0})] == ["1"]
    assert (
        len(
            oracle.expected_rows(
                rows, {"startDate": "2026-09-21", "endDate": "2026-09-21", "statuses": "0,5"}
            )
        )
        == 8
    )
    assert oracle.expected_rows(rows, {"endDate": "2026-09-20"}) == []
    with pytest.raises(ValueError, match="filter_unsupported"):
        oracle.expected_rows(rows, {"silentlyIgnored": "bad"})
    with pytest.raises(ValueError, match="coverage_gap"):
        oracle.query_for_preset("combined", [], {})


def test_page_ties_and_total_duplicates_wrong_scope():
    _, oracle, _, _, _ = modules()
    expected = oracle.expected_rows(facts(), {})
    query = {"pageSize": 3, "pageNum": 1}
    # 时间并列组[7,6]的合法边界成员可以取任一，不能硬编码ID排序。
    good = {"data": {"rows": [{"id": "8"}, {"id": "6"}, {"id": "7"}], "total": 8}}
    assert oracle.compare_page(expected, good, query)[0] == oracle.EMPTY_DIFF
    for rows, total, key in [
        (["8", "7"], 8, "problems"),
        (["8", "7", "foreign"], 8, "extra_ids"),
        (["8", "7", "7"], 8, "duplicate_ids"),
        (["8", "7", "6"], 9, "problems"),
    ]:
        actual = {"data": {"rows": [{"id": key} for key in rows], "total": total}}
        assert oracle.compare_page(expected, actual, query)[0][key]


class ResponseTransport(TransportAdapter):
    def __init__(self, responses):
        self.responses, self.requests = responses, []

    def send(self, request, context, case):
        self.requests.append(request)
        if "/role_info" in request.url:
            return ResponseSnapshot(
                status_code=200,
                body={
                    "code": 200,
                    "data": {
                        "userId": "7",
                        "tenantId": "11",
                        "deptId": "22",
                        "name": "customer-sentinel",
                    },
                },
            )
        body = self.responses(request, case)
        return ResponseSnapshot(status_code=200, body=body)


def compiled_pack(preset, source):
    _, _, _, pack, compiler = modules()
    draft = dict(pack.reception_drafts("target", "identity", "binding", "7", source["id"]))[preset]
    schema = importlib.import_module("pyta_platform_backend.schemas.assets")
    normalized = compiler.dump(schema.ScenarioDraft(**draft))
    assert compiler.preflight(normalized)["valid"]
    definition = compiler.compile_scenario(
        {"id": "scenario", "version": 1, "hash": "hash", "data": normalized}, scope_id="s0"
    )
    for case in definition.cases:
        case.metadata["context_binding_id"] = "s0"
    definition.metadata["business_database_plan"] = {"s0": source}
    definition.metadata["scopes"]["s0"].update(
        host="https://api-test.yanjiai.com", identity={"tenant_id": "11", "project_id": "22"}
    )
    return definition


@pytest.mark.parametrize("fault", ["none", "missing", "extra", "total", "duplicate", "changed"])
def test_engine_database_integration_faults(configured, monkeypatch, fault):
    import time

    source, snapshot = configured
    _, oracle, plugins, _, _ = modules()
    rows = facts()
    calls = [0]

    def read(*args, **kwargs):
        calls[0] += 1
        stamp = "changed" if fault == "changed" and calls[0] > 1 else "stable"
        return deepcopy(rows), stamp

    monkeypatch.setattr(plugins, "read_facts", read)
    definition = compiled_pack("default", source)
    expected = oracle.expected_rows(rows, {"recordDurationStatus": 2})

    def response(request, case):
        ids = [row["id"] for row in expected]
        if fault == "missing":
            ids.pop()
        elif fault == "extra":
            ids[0] = "other-project-id"
        elif fault == "duplicate":
            ids[0] = ids[1]
        return {
            "code": 200,
            "data": {
                "total": len(expected) + (fault == "total"),
                "rows": [
                    {"id": key, "name": "customer-sentinel", "phone": "phone-sentinel"}
                    for key in ids
                ],
            },
        }

    transport = ResponseTransport(response)
    plugin = plugins.BusinessDatabasePlugin(
        {"s0": source}, {"s0": snapshot}, deadline=time.monotonic() + 10
    )
    plugin.prepare(definition)
    result = FlowEngine(transport=transport, plugins=[plugin]).execute_run(definition)
    assert result.status.value == (
        "passed" if fault == "none" else "error" if fault == "changed" else "failed"
    )
    serialized = result.model_dump_json()
    assert "customer-sentinel" not in serialized and "phone-sentinel" not in serialized
    if fault == "changed":
        assert "data_changed" in serialized
    else:
        assert result.cases[-1].steps[0].assertions[-1].rule_version == oracle.CONTRACT


def test_sweep_expands_recorded_requests_and_detects_cross_page_duplicates(configured, monkeypatch):
    import time

    source, snapshot = configured
    _, oracle, plugins, _, _ = modules()
    rows = facts()
    monkeypatch.setattr(plugins, "read_facts", lambda *args, **kwargs: (deepcopy(rows), "stable"))
    definition = compiled_pack("sweep", source)
    definition.cases[-1].request.query["pageSize"] = 3
    plugin = plugins.BusinessDatabasePlugin(
        {"s0": source}, {"s0": snapshot}, deadline=time.monotonic() + 10
    )
    plugin.prepare(definition)
    assert len(definition.cases) == 3  # identity + two genuine pages for four duration2 records
    assert len({case.case_id for case in definition.cases}) == 3
    wanted = oracle.expected_rows(rows, {"recordDurationStatus": 2})

    def response(request, case):
        page = int(request.query["pageNum"])
        ids = [row["id"] for row in wanted[(page - 1) * 3 : page * 3]]
        if page == 2:
            ids = [wanted[0]["id"]]
        return {"code": 200, "data": {"total": 4, "rows": [{"id": key} for key in ids]}}

    transport = ResponseTransport(response)
    result = FlowEngine(transport=transport, plugins=[plugin]).execute_run(definition)
    assert result.status.value == "failed"
    assert len(transport.requests) == 3
    assert result.cases[-1].steps[0].assertions[-1].actual["duplicate_ids"]


def test_compiler_requires_identity_diff_assertion_and_known_filters(configured):
    _, _, _, pack, compiler = modules()
    source, _ = configured
    raw = next(pack.reception_drafts("target", "identity", "binding", "7", source["id"]))[1]
    raw["steps"][1]["depends_on"] = []
    assert not compiler.preflight(raw)["valid"]
    raw["steps"][1]["depends_on"] = ["identity"]
    raw["steps"][1]["request"]["query"]["unknown"] = "bad"
    assert not compiler.preflight(raw)["valid"]


def test_mysql_transaction_is_readonly_and_always_released(configured, monkeypatch):
    source, _ = configured
    sources, _, _, _, _ = modules()
    statements, released = [], []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params=None):
            statements.append(sql)

    connection = SimpleNamespace(
        cursor=Cursor,
        rollback=lambda: released.append("rollback"),
        close=lambda: released.append("close"),
    )
    monkeypatch.setattr(sources.pymysql, "connect", lambda **kwargs: connection)
    with pytest.raises(sources.BusinessDataError):
        with sources.read_connection(source):
            raise RuntimeError("db-pass-sentinel driver details")
    assert "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY" in statements
    assert released == ["rollback", "close"]


def test_asset_routes_import_publish_plan_worker_and_forgery(configured, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    source, _ = configured
    sources, oracle, plugins, _, _ = modules()
    app_module = importlib.import_module("pyta_platform_backend.app")
    settings = importlib.import_module("pyta_platform_backend.config").BackendSettings(
        app_env="test", state_db_path=str(tmp_path / "business-assets.sqlite3")
    )
    app = app_module.create_app(settings=settings)
    management = importlib.import_module("pyta_platform_backend.schemas.management")
    env = app.state.management_service.create_environment(
        management.CreateEnvironmentRequest(
            auth_mode="none", name="yanji-test", base_url="https://api-test.yanjiai.com"
        )
    )
    context = app.state.context_service
    context.save(
        "targets",
        {
            "id": "target",
            "name": "test",
            "environment_id": env.id,
            "base_url": "https://api-test.yanjiai.com",
            "requires_context": True,
            "auth": {"mode": "password", "contract_confirmed": True},
        },
        creating=True,
    )
    context.save(
        "identity-profiles",
        {
            "id": "identity",
            "name": "test",
            "target_ids": ["target"],
            "username_secret_ref": "env:PYTA_SECRET_API_USER",
            "password_secret_ref": "env:PYTA_SECRET_API_PASSWORD",
        },
        creating=True,
    )
    context.save(
        "context-bindings",
        {
            "id": "binding",
            "name": "test",
            "target_id": "target",
            "identity_id": "identity",
            "tenant_id": "11",
            "project_id": "22",
        },
        creating=True,
    )
    monkeypatch.setenv("PYTA_SECRET_API_USER", "api-user-sentinel")
    monkeypatch.setenv("PYTA_SECRET_API_PASSWORD", "api-password-sentinel")
    rows = facts()
    monkeypatch.setattr(plugins, "read_facts", lambda *args, **kwargs: (deepcopy(rows), "stable"))
    payload = {
        "target_ref": "target",
        "identity_ref": "identity",
        "binding_ref": "binding",
        "expected_user_id": "7",
        "datasource_ref": source["id"],
    }
    client = TestClient(app)
    assert client.get("/api/v1/business-datasources").json()[0]["configuration"] == "passed"
    check = client.post("/api/v1/business-datasources/yanji-test/preflight", json=payload).json()
    assert check == {
        "configuration": "passed",
        "connection": "not_verified",
        "permission": "not_verified",
        "errors": [],
    }
    imported = client.post("/api/v1/imports/yanji-reception", json=payload)
    assert imported.status_code == 201, imported.text
    assets = imported.json()["assets"]
    assert len(assets) == 11
    assert client.post("/api/v1/imports/yanji-reception", json=payload).json()["assets"] == assets
    scenario = assets[0]
    identifier = scenario["id"]
    path = "/api/v1/scenarios/" + identifier
    assert client.post(path + "/preflight").json()["valid"]
    publish = client.post(
        path + "/publish",
        json={"expected_revision": scenario["revision"], "change_note": "readonly test"},
    )
    assert publish.status_code == 201, publish.text
    plan = client.post(path + "/versions/1/plan", json={"transport_mode": "live"}).json()
    assert plan["run_definition"]["metadata"]["business_database_plan"]["s0"] == source
    assert "db-pass-sentinel" not in json.dumps(plan)
    debug = client.post(
        "/api/v1/scenarios/debug",
        json={"draft": scenario["draft"], "step_id": "receptions", "live_confirmed": True},
    )
    assert debug.status_code == 400 and "整场景调试" in debug.text
    plan["run_definition"]["metadata"].pop("fixture_plan", None)
    # 普通运行不能提交有来源计划或有数据库步骤的伪造元数据。
    schema = importlib.import_module("pyta_platform_backend.schemas.run")
    with pytest.raises(Exception) as failure:
        app.state.run_service.create_run(
            schema.CreateRunRequest(
                suite_id="forged",
                environment_id=env.id,
                payload={
                    key: value
                    for key, value in plan.items()
                    if key
                    not in {
                        "asset_ref",
                        "scenario_refs",
                        "scenario_version_ref",
                        "context_snapshots",
                    }
                },
            )
        )
    assert "业务数据库" in str(failure.value)

    expected = oracle.expected_rows(rows, {"recordDurationStatus": 2})
    context_transport = importlib.import_module("pyta_platform_backend.workers.context_transport")

    def send(self, request, context, case):
        if request.url.endswith("password_login"):
            body = {"code": 200, "data": {"token": "api-token-sentinel"}}
        elif request.url.endswith("role_info"):
            body = {"code": 200, "data": {"userId": "7", "tenantId": "11", "deptId": "22"}}
        else:
            body = {
                "code": 200,
                "data": {"total": len(expected), "rows": [{"id": row["id"]} for row in expected]},
            }
        return ResponseSnapshot(status_code=200, body=body)

    monkeypatch.setattr(context_transport.HttpxTransport, "send", send)
    queued = client.post(path + "/versions/1/runs", json={"transport_mode": "live"})
    assert queued.status_code == 202, queued.text
    result = app.state.worker_runner.run_next()
    assert result.status.value == "succeeded", result.results
    assert result.counts["passed"] == 2
    assert result.results[-1]["metadata"]["database_evidence"]["datasource_hash"] == source["hash"]
    for execution_status in ("cancelled", "timed_out"):
        with monkeypatch.context() as local_patch:
            def stop_preparation(self, definition, execution_status=execution_status):
                failure = sources.BusinessDataError("business_datasource_stopped")
                failure.execution_status = execution_status
                raise failure

            local_patch.setattr(plugins.BusinessDatabasePlugin, "prepare", stop_preparation)
            queued = client.post(path + "/versions/1/runs", json={"transport_mode": "live"})
            assert queued.status_code == 202
            stopped = app.state.worker_runner.run_next()
            assert stopped.status.value == execution_status
            assert stopped.counts["requests"] == 0

    disabled_data = deepcopy(scenario["draft"])
    disabled_data["steps"][-1]["enabled"] = False
    disabled = app.state.asset_service.create("scenarios", disabled_data)
    disabled_path = "/api/v1/scenarios/" + disabled["id"]
    assert client.post(
        disabled_path + "/publish",
        json={"expected_revision": disabled["revision"], "change_note": "disabled DB check"},
    ).status_code == 201
    monkeypatch.setenv("PYTA_BUSINESS_DATASOURCES_JSON", "[]")
    queued = client.post(disabled_path + "/versions/1/runs", json={"transport_mode": "live"})
    assert queued.status_code == 202
    disabled_result = app.state.worker_runner.run_next()
    assert disabled_result.status.value == "succeeded"
    assert disabled_result.results[-1]["status"] == "skipped"
    with pytest.raises(sources.BusinessDataError, match="missing"):
        sources.resolve_source(source["id"])


def test_permission_budget_and_connection_failure_are_explicit(configured, monkeypatch):
    import time

    source, snapshot = configured
    sources, _, _, _, _ = modules()
    with pytest.raises(sources.BusinessDataError, match="budget"):
        sources.check_budget(time.monotonic() - 1)
    with pytest.raises(sources.BusinessDataError, match="cancelled") as failure:
        sources.check_budget(should_stop=lambda: "cancelled")
    assert failure.value.execution_status == "cancelled"

    def fail_connection(**kwargs):
        raise RuntimeError("db-pass-sentinel")

    monkeypatch.setattr(sources.pymysql, "connect", fail_connection)
    result = sources.preflight_source(source["id"], snapshot, "7", execute_query=True)
    assert result["connection"] == "failed"
    assert "db-pass-sentinel" not in json.dumps(result)


def test_permission_query_and_fact_row_budget_with_bound_keyword(configured, monkeypatch):
    source, _ = configured
    sources, oracle, _, _, _ = modules()
    statements = []
    permission = [{"user_id": 7, "role_id": 9, "is_super": 1, "purpose": None}]
    rows = facts()

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params=None):
            self.sql = sql
            statements.append((sql, params))

        def fetchall(self):
            return deepcopy(permission if "FROM `user`" in self.sql else rows)

    connection = SimpleNamespace(cursor=Cursor, rollback=lambda: None, close=lambda: None)
    monkeypatch.setattr(sources.pymysql, "connect", lambda **kwargs: connection)
    keyword = "' OR 1=1 --"
    projected, _ = oracle.read_facts(source, "7", keyword)
    assert len(projected) == 8
    sql, values = statements[-1]
    assert keyword not in sql and keyword in values
    with pytest.raises(sources.BusinessDataError, match="row_budget"):
        oracle.read_facts({**source, "max_rows": 3}, "7")
    permission[0]["is_super"] = 0
    with pytest.raises(sources.BusinessDataError, match="permission_unconfirmed"):
        oracle.read_facts(source, "7")
    permission[0]["is_super"] = 1
    permission[0]["purpose"] = "unconfirmed-purpose"
    with pytest.raises(sources.BusinessDataError, match="permission_unconfirmed"):
        oracle.read_facts(source, "7")


def test_configuration_drift_rejected_before_business_http(configured, monkeypatch):
    import time

    source, snapshot = configured
    _, _, plugins, _, _ = modules()
    definition = compiled_pack("default", source)
    plugin = plugins.BusinessDatabasePlugin(
        {"s0": {**source, "hash": "old"}}, {"s0": snapshot}, deadline=time.monotonic() + 10
    )
    with pytest.raises(ValueError, match="configuration_drift"):
        plugin.prepare(definition)


def test_disabled_database_step_never_resolves_or_expands_source(configured, monkeypatch):
    import time

    source, _ = configured
    _, _, plugins, _, _ = modules()
    definition = compiled_pack("sweep", source)
    definition.cases[-1].enabled = False
    plugin = plugins.BusinessDatabasePlugin({}, {}, deadline=time.monotonic() + 10)

    def unexpected(*args, **kwargs):
        pytest.fail("禁用步骤不应解析或连接业务来源")

    monkeypatch.setattr(plugin, "source", unexpected)
    plugin.prepare(definition)
    assert len(definition.cases) == 2
    assert definition.cases[-1].enabled is False


def test_keyword_sweep_uses_same_projection_and_rewires_dependents(configured, monkeypatch):
    import time

    source, snapshot = configured
    _, oracle, plugins, _, _ = modules()
    rows = facts()

    def read(source, check_user, keyword="", **kwargs):
        projected = deepcopy(rows)
        for row in projected:
            row["keyword_hit"] = int(not keyword or row["id"] == keyword)
        return projected, "keyword:" + keyword

    monkeypatch.setattr(plugins, "read_facts", read)
    definition = compiled_pack("sweep", source)
    original_id = definition.cases[-1].case_id
    definition.cases[-1].request.query["keyword"] = "1"
    dependent = deepcopy(definition.cases[0])
    dependent.case_id = "s0__after_sweep"
    dependent.depends_on = [original_id]
    definition.cases.append(dependent)
    cleanup = deepcopy(dependent)
    cleanup.case_id = "s0__cleanup"
    definition.cleanup_cases = [cleanup]
    plugin = plugins.BusinessDatabasePlugin(
        {"s0": source}, {"s0": snapshot}, deadline=time.monotonic() + 10
    )
    plugin.prepare(definition)
    expanded_id = original_id + "__page_1"
    assert definition.cases[-1].depends_on == [expanded_id]
    assert definition.cleanup_cases[0].depends_on == [expanded_id]
    assert plugin.sweeps[original_id]["fingerprint"] == "keyword:1"

    def response(request, case):
        return {"code": 200, "data": {"total": 1, "rows": [{"id": "1"}]}}

    result = FlowEngine(transport=ResponseTransport(response), plugins=[plugin]).execute_run(
        definition
    )
    assert result.status.value == "passed", result.model_dump_json()
    assert result.cases[-1].status.value == "passed"


def test_database_identity_requires_exact_native_comparison(configured):
    source, _ = configured
    _, _, _, pack, compiler = modules()
    raw = next(pack.reception_drafts("target", "identity", "binding", "7", source["id"]))[1]
    assertion = next(a for a in raw["steps"][0]["assertions"] if a["selector"] == "data.userId")
    assertion.update(value_type="decimal", tolerance=100)
    assert not compiler.preflight(raw)["valid"]


@pytest.mark.parametrize("cross_page_duplicate", [False, True])
def test_sweep_detects_duplicates_across_valid_time_tied_pages(
    configured, monkeypatch, cross_page_duplicate
):
    import time

    source, snapshot = configured
    _, oracle, plugins, _, _ = modules()
    rows = facts()
    for row in rows:
        row["create_time"] = rows[0]["create_time"]
    monkeypatch.setattr(plugins, "read_facts", lambda *args, **kwargs: (deepcopy(rows), "stable"))
    definition = compiled_pack("sweep", source)
    definition.cases[-1].request.query["pageSize"] = 3
    plugin = plugins.BusinessDatabasePlugin(
        {"s0": source}, {"s0": snapshot}, deadline=time.monotonic() + 10
    )
    plugin.prepare(definition)

    def response(request, case):
        ids = ["5", "3", "1"] if request.query["pageNum"] == 1 else [
            "1" if cross_page_duplicate else "7"
        ]
        body = {"code": 200, "data": {"total": 4, "rows": [{"id": key} for key in ids]}}
        # 每页在同时间等价组内均合法，只有完整多重集合能发现跨页重复/遗漏。
        assert oracle.compare_page(oracle.expected_rows(rows, {"recordDurationStatus": 2}),
                                   body, request.query)[0] == oracle.EMPTY_DIFF
        return body

    result = FlowEngine(transport=ResponseTransport(response), plugins=[plugin]).execute_run(
        definition
    )
    assert result.status.value == ("failed" if cross_page_duplicate else "passed")
    if cross_page_duplicate:
        diff = result.cases[-1].steps[0].assertions[-1].actual
        assert diff["duplicate_ids"] == ["1"]
        assert diff["missing_ids"] == ["7"]

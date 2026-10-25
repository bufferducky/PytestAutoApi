"""业务断言和异步终态：明确缺失/空值、精确对象、预算、重试与首错。"""

import pytest

from testflow_engine import (
    AssertionSpec,
    CallableTransport,
    ExecutionContext,
    RequestSpec,
    ResponseSnapshot,
)
from testflow_engine import TestCaseDefinition as Case
from testflow_engine import TestFlowEngine as Engine
from testflow_engine import TestRunDefinition as Run
from testflow_engine.assertions import AssertionEngine
from testflow_engine.executor.waiting import RequestStopped, WaitExecutor
from testflow_engine.models.core import WaitPolicy


def evaluate(spec, body, variables=None):
    return AssertionEngine().evaluate(
        AssertionSpec(**spec),
        ResponseSnapshot(status_code=200, body=body),
        ExecutionContext(run_id="assert", variables=variables or {}),
    )


@pytest.mark.parametrize(
    ("body", "operator", "expected_status", "missing"),
    [
        ({}, "equals", "error", True),
        ({"value": None}, "equals", "passed", False),
        ({}, "is_missing", "passed", True),
        ({"value": None}, "is_missing", "failed", False),
        ({"value": None}, "is_null", "passed", False),
        ({"value": ""}, "is_null", "failed", False),
        ({"value": []}, "is_null", "failed", False),
        ({}, "exists", "failed", True),
        ({"value": None}, "exists", "passed", False),
    ],
)
def test_missing_null_empty_and_existence_are_distinct(body, operator, expected_status, missing):
    result = evaluate({"name": "value", "selector": "value", "operator": operator}, body)
    assert result.status.value == expected_status and result.actual_missing == missing


def test_code_200_but_wrong_object_binding_is_failed_even_if_list_is_reordered():
    spec = {
        "name": "exact binding",
        "selector": "data.records",
        "expected_ref": "fixtures.package.id",
        "select_by": {"key": "id", "value_ref": "fixtures.person.id", "field": "package_id"},
    }
    variables = {"fixtures": {"person": {"id": "wanted"}, "package": {"id": "expected-package"}}}
    body = {
        "code": 200,
        "data": {
            "records": [
                {"id": "other", "package_id": "expected-package"},
                {"id": "wanted", "package_id": "wrong-package"},
            ]
        },
    }
    result = evaluate(spec, body, variables)
    assert result.status.value == "failed" and result.actual == "wrong-package"
    body["data"]["records"][1]["package_id"] = "expected-package"
    body["data"]["records"].reverse()
    assert evaluate(spec, body, variables).status.value == "passed"
    body["data"]["records"].append(body["data"]["records"][0])
    assert evaluate(spec, body, variables).status.value == "error"


def test_missing_expected_reference_is_not_implicitly_none():
    result = evaluate(
        {"name": "expected", "selector": "value", "expected_ref": "outputs.before.id"},
        {"value": None},
    )
    assert result.status.value == "error" and "引用不存在" in result.message


@pytest.mark.parametrize(
    ("spec", "body", "variables", "status"),
    [
        (
            {
                "operator": "keyed_equals",
                "expected": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}],
            },
            {"value": [{"id": 2, "value": "b"}, {"id": 1, "value": "a"}]},
            {},
            "passed",
        ),
        ({"operator": "unique"}, {"value": ["a", "a"]}, {}, "failed"),
        ({"operator": "unique"}, {"value": [1, "1"]}, {}, "passed"),
        (
            {
                "operator": "schema",
                "expected": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                },
            },
            {"value": {"id": 1}},
            {},
            "failed",
        ),
        (
            {"rule_ref": "count_delta@1", "baseline_ref": "outputs.before", "expected": 1},
            {"value": [1, 2, 3]},
            {"outputs": {"before": [1, 2]}},
            "passed",
        ),
        (
            {"rule_ref": "unchanged@1", "baseline_ref": "outputs.before"},
            {"value": {"id": "other", "state": "changed"}},
            {"outputs": {"before": {"id": "other", "state": "original"}}},
            "failed",
        ),
        ({"rule_ref": "arbitrary-code@1"}, {"value": 1}, {}, "error"),
    ],
)
def test_structures_relations_and_invariant_rules(spec, body, variables, status):
    result = evaluate({"name": "rule", "selector": "value", **spec}, body, variables)
    assert result.status.value == status
    assert result.rule_version == spec.get("rule_ref", "builtin@1")


@pytest.mark.parametrize(
    ("value", "expected", "kind", "normalization", "tolerance", "status"),
    [
        (0.1 + 0.2, "0.3", "decimal", {}, 1e-12, "passed"),
        ("0.10", "0.1", "decimal", {}, 0, "passed"),
        ("NaN", "1", "decimal", {}, 0, "error"),
        ("2026-10-25T08:00:00+08:00", "2026-10-25T00:00:00Z", "datetime", {}, 0, "passed"),
        (
            "2026-10-25T08:00:00",
            "2026-10-25T00:00:00Z",
            "datetime",
            {"timezone": "Asia/Shanghai"},
            0,
            "passed",
        ),
        ("2026-10-25T08:00:00", "2026-10-25T00:00:00Z", "datetime", {}, 0, "error"),
        (1792886400000, 1792886400, "datetime", {"unit": "milliseconds"}, 0, "failed"),
    ],
)
def test_explicit_decimal_and_time_semantics(
    value, expected, kind, normalization, tolerance, status
):
    result = evaluate(
        {
            "name": "typed",
            "selector": "value",
            "expected": expected,
            "value_type": kind,
            "normalization": normalization,
            "tolerance": tolerance,
        },
        {"value": value},
    )
    assert result.status.value == status, result.message


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


def policy(**extra):
    return WaitPolicy(
        state_selector="data.state",
        state_map={"queued": "pending", "working": "running", "ok": "succeeded", "bad": "failed"},
        contract_confirmed=True,
        **extra,
    )


def wait_case(wait_policy):
    return Case(
        case_id="wait",
        title="wait",
        request=RequestSpec(url="https://example.test/status"),
        wait_policy=wait_policy,
        metadata={"operation_kind": "query", "query_contract_confirmed": True},
        assertions=[AssertionSpec(name="code", selector="code", expected=200)],
    )


def execute_states(states, wait_policy=None):
    clock = Clock()
    calls = []
    sequence = iter(states)

    def send(request, context, case):
        value = next(sequence)
        calls.append(value)
        if isinstance(value, Exception):
            raise value
        return ResponseSnapshot(status_code=200, body={"code": 200, "data": {"state": value}})

    context = ExecutionContext(run_id="wait")
    executor = WaitExecutor(
        CallableTransport(send), AssertionEngine(), clock=clock, sleeper=clock.sleep
    )
    case = wait_case(wait_policy or policy())
    return executor, context, case, calls, clock


def test_virtual_clock_polling_success_and_first_last_trace_bounded():
    executor, context, case, calls, clock = execute_states(
        ["queued", "working", "working", "working", "ok"], policy(interval_seconds=1, trace_limit=2)
    )
    response = executor.send(case.request, context, case)
    assert response.body["data"]["state"] == "ok" and len(calls) == 5
    assert context.artifacts["poll_attempts"]["wait"] == 5 and clock.now == pytest.approx(4)
    assert [row["state"] for row in context.artifacts["poll_trace"]["wait"]] == [
        "pending",
        "succeeded",
    ]
    assert len(context.artifacts["network_attempts"]["wait"]) == 2
    assert context.artifacts["network_attempt_count"]["wait"] == 5


@pytest.mark.parametrize(
    ("states", "wait_policy", "status", "count"),
    [
        (["queued", "bad"], policy(), "failed", 2),
        (["queued", "unexpected"], policy(), "error", 2),
        (["working", "queued"], policy(), "error", 2),
        (["queued", "queued"], policy(max_attempts=2), "timed_out", 2),
        (["queued"] * 10, policy(interval_seconds=1, deadline_seconds=1.5), "timed_out", 2),
    ],
)
def test_failure_unknown_regression_attempt_and_deadline_stop(states, wait_policy, status, count):
    executor, context, case, calls, clock = execute_states(states, wait_policy)
    with pytest.raises(RequestStopped) as exc:
        executor.send(case.request, context, case)
    assert exc.value.execution_status == status and len(calls) == count
    assert exc.value.response is not None


def test_transient_query_retries_preserve_errors_but_write_never_retries():
    executor, context, case, calls, clock = execute_states(
        [ConnectionError("first"), ConnectionError("second"), "ok"], policy(network_retries=2)
    )
    assert executor.send(case.request, context, case).status_code == 200
    assert [row.get("error_type") for row in context.artifacts["network_attempts"]["wait"]] == [
        "ConnectionError",
        "ConnectionError",
        None,
    ]
    assert len(calls) == 3
    executor, context, case, calls, clock = execute_states(["ok"], policy(network_retries=2))
    case.metadata["operation_kind"] = "write"
    with pytest.raises(RequestStopped):
        executor.send(case.request, context, case)
    assert calls == []


def test_wait_budget_status_and_cleanup_are_preserved_by_engine():
    calls = []

    def send(request, context, case):
        calls.append(case.case_id)
        return ResponseSnapshot(status_code=200, body={"code": 200, "data": {"state": "queued"}})

    waiting = wait_case(policy(interval_seconds=0, max_attempts=2))
    cleanup = Case(
        case_id="cleanup",
        title="cleanup",
        request=RequestSpec(url="https://example.test/cleanup"),
        assertions=[AssertionSpec(name="code", selector="code", expected=200)],
    )
    result = Engine(transport=CallableTransport(send)).execute_run(
        Run(cases=[waiting], cleanup_cases=[cleanup])
    )
    assert result.status.value == "timed_out" and result.cleanup_status == "succeeded"
    assert calls == ["wait", "wait", "cleanup"]
    assert result.cases[0].steps[0].poll_attempts == 2
    assert result.cases[0].steps[0].response.body["data"]["state"] == "queued"


def test_registered_code_rule_has_declared_inputs_and_errors_are_not_failures(monkeypatch):
    from testflow_engine.assertions.business import CUSTOM_RULES

    def broken(**kwargs):
        raise RuntimeError("controlled rule broke")

    monkeypatch.setitem(CUSTOM_RULES, "broken@1", (broken, ("outputs.before",)))
    result = evaluate(
        {"name": "custom", "selector": "value", "rule_ref": "broken@1"},
        {"value": 1},
        {"outputs": {"before": 1}},
    )
    assert result.status.value == "error" and result.rule_version == "broken@1"
    assert "controlled rule broke" in result.message

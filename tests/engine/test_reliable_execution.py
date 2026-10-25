"""插件异常、清理预算和请求模板不可变性的行为回归。"""

import time

import pytest

from testflow_engine import (
    AssertionSpec,
    CallableTransport,
    EnginePlugin,
    RequestSpec,
    ResponseSnapshot,
)
from testflow_engine import TestCaseDefinition as Case
from testflow_engine import TestFlowEngine as Engine
from testflow_engine import TestRunDefinition as Run


def make_case(name):
    return Case(
        case_id=name,
        title=name,
        request=RequestSpec(url="https://example.test"),
        assertions=[AssertionSpec(name="code", selector="code", expected=200)],
    )


@pytest.mark.parametrize(
    "hook", ["before_run", "before_case", "after_response", "after_case", "after_run"]
)
def test_hook_exceptions_have_error_result_and_cleanup(hook):
    calls = []

    class Broken(EnginePlugin):
        pass

    def fail(**kwargs):
        if kwargs.get("case") and kwargs["case"].case_id == "cleanup":
            return
        raise RuntimeError("hook failed")

    setattr(Broken, hook, staticmethod(fail))
    engine = Engine(
        transport=CallableTransport(
            lambda request, context, case: (
                calls.append(case.case_id) or ResponseSnapshot(status_code=200, body={"code": 200})
            )
        ),
        plugins=[Broken()],
    )
    result = engine.execute_run(
        Run(cases=[make_case("main")], cleanup_cases=[make_case("cleanup")])
    )
    assert result.status.value == "error"
    assert "cleanup" in calls
    assert result.cleanup_status == "succeeded"


def test_cleanup_budget_exhaustion_is_reported_without_more_requests():
    calls, evidence = [], []

    def send(request, context, case):
        calls.append(case.case_id)
        if case.case_id == "cleanup1":
            time.sleep(0.02)
        return ResponseSnapshot(status_code=200, body={"code": 200})

    result = Engine(transport=CallableTransport(send)).execute_run(
        Run(
            cases=[make_case("main")], cleanup_cases=[make_case("cleanup1"), make_case("cleanup2")]
        ),
        cleanup_timeout_seconds=0.01,
        on_case_result=lambda case, phase: evidence.append((case, phase)),
    )
    assert calls == ["main", "cleanup1"]
    assert result.cleanup_status == "cleanup_failed"
    assert evidence[-1][0].status.value == "blocked"


def test_execution_uses_private_template_copy():
    class Mutates(EnginePlugin):
        def before_case(self, case, context):
            case.request.headers["Authorization"] = "private"

    source = Run(cases=[make_case("main")])
    engine = Engine(
        transport=CallableTransport(
            lambda request, context, case: ResponseSnapshot(status_code=200, body={"code": 200})
        ),
        plugins=[Mutates()],
    )
    assert engine.execute_run(source).status.value == "passed"
    assert source.cases[0].request.headers == {}

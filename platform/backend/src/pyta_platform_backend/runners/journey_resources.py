"""UI旅程复用R04资源生命周期与R05断言；不在UI定位器中发送业务HTTP。"""

from time import monotonic
from types import SimpleNamespace

from pyta_platform_backend.workers.context_transport import ContextTransport
from pyta_platform_backend.workers.resource_plugin import ResourcePlugin
from testflow_engine import ExecutionContext, RequestSpec
from testflow_engine import TestCaseDefinition as Case
from testflow_engine import TestFlowEngine as Engine


class JourneyResources:
    def __init__(
        self,
        repository,
        snapshots,
        requirements,
        variables,
        run_id,
        deadline,
        redactor,
        should_stop=None,
    ):
        self.context = ExecutionContext(run_id=run_id, variables=variables)
        self.context.variables["host"] = snapshots["default"]["target"]["base_url"]
        self.context.plugin_state["execution"] = {
            "phase": "main",
            "deadline_monotonic": deadline,
            "should_stop": should_stop,
        }
        self.deadline = deadline
        self.transport = ContextTransport(
            snapshots,
            remember_secret=redactor._collect,
            timeout_seconds=max(0.001, deadline - monotonic()),
        )
        self.plugin = ResourcePlugin(
            repository, self.transport, snapshots, {"journey": requirements}, redactor=redactor
        )
        self.scope = Case(
            case_id="journey_resources",
            title="旅程资源",
            request=RequestSpec(url=self.context.variables["host"]),
            metadata={"scope_id": "journey", "context_binding_id": "default"},
        )
        self.closed = False

    def prepare(self):
        self.plugin.before_case(self.scope, self.context)

    def check(self):
        self.plugin.before_case(self.scope, self.context)

    def assert_api(self, action):
        self.check()
        case = Case(
            case_id=action["step_id"],
            title=action["name"],
            request=action["request"],
            assertions=action["assertions"],
            metadata={
                "context_binding_id": "default",
                "operation_kind": "query",
                "query_contract_confirmed": True,
            },
        )
        result = Engine(transport=self.transport).execute_case(
            case, self.context, deadline=self.deadline
        )
        return result.steps[0]

    def close(self, cleanup_status="succeeded"):
        if self.closed:
            return cleanup_status
        self.closed = True
        result = SimpleNamespace(cleanup_status=cleanup_status)
        self.context.plugin_state["execution"] = {
            "phase": "cleanup",
            "deadline_monotonic": monotonic() + 60,
        }
        try:
            self.plugin.after_run(result, self.context)
            return result.cleanup_status
        finally:
            self.transport.close()

"""
测试执行器骨架。

执行链路固定为：
run -> case -> transport -> assertion -> report

这条链路是新引擎最核心的主干，后续无论挂 FastAPI 接口、异步 worker、
还是平台 UI 触发执行，都应该尽量复用这里，而不是复制一套流程。
"""

from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic

from ..assertions import AssertionEngine
from ..models import (
    CaseExecutionResult,
    ExecutionContext,
    ExecutionStatus,
    ExtractionSource,
    RunExecutionResult,
    StepExecutionResult,
    TestCaseDefinition,
    TestRunDefinition,
)
from ..reporting import ReportCollector
from .rendering import RequestTemplateRenderer
from .transport import TransportAdapter, TransportNotConfiguredError
from .waiting import WaitExecutor


class TestFlowEngine:
    """新测试引擎主执行器。"""

    def __init__(
        self,
        transport: TransportAdapter = None,
        assertion_engine: AssertionEngine = None,
        plugins=None,
        report_collector: ReportCollector = None,
        request_renderer: RequestTemplateRenderer = None,
    ) -> None:
        self.transport = transport
        self.assertion_engine = assertion_engine or AssertionEngine()
        self.plugins = list(plugins or [])
        self.report_collector = report_collector or ReportCollector()
        self.request_renderer = request_renderer or RequestTemplateRenderer()

    def execute_run(
        self,
        run: TestRunDefinition,
        *,
        on_case_result=None,
        should_stop=None,
        timeout_seconds=300,
        cleanup_timeout_seconds=60,
    ) -> RunExecutionResult:
        """运行自己的模板副本；停止主流程后仍进入独立预算的清理。"""
        run = deepcopy(run)
        if not run.cases:
            raise ValueError("run.cases 不能为空")
        started_at = datetime.now(timezone.utc)
        deadline = monotonic() + timeout_seconds
        context = ExecutionContext(run_id=run.run_id, variables=deepcopy(run.variables))
        context.plugin_state["execution"] = {
            "phase": "main",
            "should_stop": should_stop,
            "deadline_monotonic": deadline,
        }
        scoped_contexts = {}

        def case_context(case):
            scope = case.metadata.get("scope_id")
            if not scope:
                return context
            if scope not in scoped_contexts:
                scoped_contexts[scope] = ExecutionContext(
                    run_id=run.run_id,
                    variables={
                        **deepcopy(context.variables),
                        **deepcopy(run.metadata["scopes"][scope]),
                    },
                    plugin_state=context.plugin_state,
                )
            scoped_contexts[scope].plugin_state = context.plugin_state
            return scoped_contexts[scope]

        case_results, outcomes = [], {}
        status, error, cleanup_status = None, None, "succeeded"
        try:
            stop = should_stop() if should_stop else None
            if not stop and monotonic() < deadline:
                for plugin in self.plugins:
                    plugin.before_run(run=run, context=context)
            for case in run.cases:
                stop = should_stop() if should_stop else None
                if stop or monotonic() >= deadline:
                    status = ExecutionStatus(stop or "timed_out")
                    break
                if any(outcomes.get(dep) != ExecutionStatus.PASSED for dep in case.depends_on):
                    result = self._blocked(case, "前置步骤未通过或缺失")
                else:
                    result = self.execute_case(case, case_context(case), deadline=deadline)
                case_results.append(result)
                outcomes[case.case_id] = result.status
                if result.status in {ExecutionStatus.TIMED_OUT, ExecutionStatus.CANCELLED}:
                    status = result.status
                if on_case_result:
                    on_case_result(result, "main")
                stop = should_stop() if should_stop else None
                if status in {ExecutionStatus.TIMED_OUT, ExecutionStatus.CANCELLED}:
                    break
                if stop or monotonic() >= deadline:
                    status = ExecutionStatus(stop or "timed_out")
                    break
        except Exception as exc:
            status, error = ExecutionStatus.ERROR, str(exc)
        finally:
            # 未运行的步骤也有明确证据；不把它们漏掉再报全绿。
            for case in run.cases[len(case_results) :]:
                result = self._blocked(case, error or "主流程已停止")
                case_results.append(result)
                if on_case_result:
                    on_case_result(result, "main")
            cleanup_deadline = monotonic() + cleanup_timeout_seconds
            context.plugin_state["execution"] = {
                "phase": "cleanup",
                "should_stop": None,
                "deadline_monotonic": cleanup_deadline,
            }
            for case in run.cleanup_cases:
                if monotonic() >= cleanup_deadline:
                    result = self._blocked(case, "清理预算已用尽")
                else:
                    result = self.execute_case(case, case_context(case), deadline=cleanup_deadline)
                if monotonic() >= cleanup_deadline and result.status == ExecutionStatus.PASSED:
                    result.status = ExecutionStatus.TIMED_OUT
                    result.error = "清理步骤超过总预算"
                if result.status != ExecutionStatus.PASSED:
                    cleanup_status = "cleanup_failed"
                if on_case_result:
                    on_case_result(result, "cleanup")
        summary = self.report_collector.build_summary(case_results)
        result = RunExecutionResult(
            run_id=run.run_id,
            name=run.name,
            status=status or self._resolve_run_status(summary),
            cases=case_results,
            summary=summary,
            error=error,
            cleanup_status=cleanup_status,
            authentication_results=context.artifacts.get("authentication", []),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
        for plugin in self.plugins:
            try:
                plugin.after_run(result=result, context=context)
            except Exception as exc:
                result.status, result.error = ExecutionStatus.ERROR, str(exc)
        return result

    @staticmethod
    def _blocked(case, message):
        now = datetime.now(timezone.utc)
        return CaseExecutionResult(
            case_id=case.case_id,
            title=case.title,
            metadata={**deepcopy(case.metadata), "depends_on": list(case.depends_on)},
            status=ExecutionStatus.BLOCKED,
            error=message,
            steps=[],
            started_at=now,
            finished_at=now,
        )

    def execute_case(self, case, context, *, deadline=None) -> CaseExecutionResult:
        started_at = datetime.now(timezone.utc)
        step = StepExecutionResult(
            name="request",
            status=ExecutionStatus.PENDING,
            started_at=started_at,
            finished_at=started_at,
        )
        result = CaseExecutionResult(
            case_id=case.case_id,
            title=case.title,
            metadata={**deepcopy(case.metadata), "depends_on": list(case.depends_on)},
            status=ExecutionStatus.PENDING,
            steps=[step],
            started_at=started_at,
            finished_at=started_at,
        )
        try:
            if not case.enabled:
                result.status, result.steps = ExecutionStatus.SKIPPED, []
                return result
            for plugin in self.plugins:
                plugin.before_case(case=case, context=context)
            if self.transport is None:
                raise TransportNotConfiguredError("TestFlowEngine 尚未配置 transport")
            request = self.request_renderer.render(request=case.request, context=context)
            if deadline is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError("运行预算已用尽")
                request.timeout_seconds = min(request.timeout_seconds, remaining)
            step.request = request
            step.request_sent = True
            response = WaitExecutor(self.transport, self.assertion_engine).send(
                request, context, case, deadline
            )
            step.response = response
            for plugin in self.plugins:
                plugin.after_response(case=case, response=response, context=context)
            self._apply_extractors(case=case, response=response, context=context)
            step.assertions = self.assertion_engine.evaluate_all(
                assertions=case.assertions,
                response=response,
                context=context,
            )
            result.status = step.status = self._resolve_step_status(step.assertions)
            self._notify_after_case(case=case, result=result, context=context)
        except Exception as exc:
            result.status = step.status = ExecutionStatus(getattr(exc, "execution_status", "error"))
            if getattr(exc, "response", None) is not None:
                step.response = exc.response
            result.error = step.error = str(exc)
            step.error_type = getattr(exc, "category", type(exc).__name__)
            if getattr(exc, "request_sent", None) is False:
                step.request_sent = False
        finally:
            attempts = context.artifacts.get("http_attempts", {}).get(case.case_id, [])
            step.attempts = list(attempts)
            step.http_attempt_count = getattr(
                attempts, "request_count", len([e for e in attempts if e.get("kind") == "request"])
            )
            step.http_replay_count = getattr(
                attempts, "replay_count", len([e for e in attempts if e.get("replay") == 1])
            )
            step.poll_trace = context.artifacts.get("poll_trace", {}).get(case.case_id, [])
            step.poll_attempts = context.artifacts.get("poll_attempts", {}).get(case.case_id, 0)
            step.network_attempt_count = context.artifacts.get("network_attempt_count", {}).get(
                case.case_id, 0
            )
            step.network_attempts = context.artifacts.get("network_attempts", {}).get(
                case.case_id, []
            )
            if any(attempt.get("kind") == "request" for attempt in step.attempts):
                step.request_sent = True
            result.finished_at = step.finished_at = datetime.now(timezone.utc)
        return result

    def _notify_after_case(
        self,
        case: TestCaseDefinition,
        result: CaseExecutionResult,
        context: ExecutionContext,
    ) -> None:
        """统一处理 after_case，避免多个出口漏调插件。"""

        for plugin in self.plugins:
            plugin.after_case(case=case, result=result, context=context)

    def _apply_extractors(
        self,
        case: TestCaseDefinition,
        response,
        context: ExecutionContext,
    ) -> None:
        """执行标准化变量提取。

        这是新框架里对“上一条请求产出的值，后续请求还要继续用”的正式支持。
        第一阶段先覆盖最常见的场景：
        - 从响应体里提取 ID / token / code
        - 从响应头里提取追踪信息
        - 把结果写到 `context.variables` 的指定路径
        """

        for extractor in case.extractors:
            actual = self._resolve_extractor_value(extractor=extractor, response=response)
            if actual is None and extractor.required:
                raise ValueError("必需提取值缺失: " + extractor.target)
            self._write_context_value(context=context, target=extractor.target, value=actual)

    def _resolve_extractor_value(self, extractor, response):
        """根据提取规则从响应里取值。"""

        if extractor.source == ExtractionSource.STATUS_CODE:
            return response.status_code
        if extractor.source == ExtractionSource.RESPONSE_HEADERS:
            return self.assertion_engine._extract_value(
                source=response.headers,
                selector=extractor.selector,
                selector_type=extractor.selector_type,
            )
        return self.assertion_engine._extract_value(
            source=response.body,
            selector=extractor.selector,
            selector_type=extractor.selector_type,
            response=response,
        )

    @staticmethod
    def _write_context_value(context: ExecutionContext, target: str, value) -> None:
        """把提取值写回上下文变量。

        target 用点路径表示，例如：
        - `cache.persona_id`
        - `auth.login_code`
        - `runtime.last_status`
        """

        if not target:
            return

        parts = [part for part in target.split(".") if part]
        if not parts:
            return

        current = context.variables
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value

    @staticmethod
    def _resolve_step_status(assertion_results) -> ExecutionStatus:
        """根据断言结果计算步骤状态。"""

        if any(result.status == ExecutionStatus.ERROR for result in assertion_results):
            return ExecutionStatus.ERROR
        if any(result.status != ExecutionStatus.PASSED for result in assertion_results):
            return ExecutionStatus.FAILED
        return ExecutionStatus.PASSED

    @staticmethod
    def _resolve_run_status(summary) -> ExecutionStatus:
        """根据 summary 计算 run 状态。"""

        if summary.errors:
            return ExecutionStatus.ERROR
        if summary.failed:
            return ExecutionStatus.FAILED
        if summary.blocked:
            return ExecutionStatus.BLOCKED
        if summary.passed == 0 and summary.skipped == summary.total:
            return ExecutionStatus.SKIPPED
        if summary.assertions == 0:
            return ExecutionStatus.BLOCKED
        return ExecutionStatus.PASSED

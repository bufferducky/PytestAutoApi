"""有限查询轮询与传输重试，共享总预算，永不重试业务写操作。"""

import math
from datetime import datetime, timezone
from time import monotonic, sleep

from .._field_path import has_field_path, resolve_field_path
from ..models import ExecutionStatus


class RequestStopped(RuntimeError):
    request_sent = True

    def __init__(self, message, status="timed_out", response=None):
        super().__init__(message)
        self.execution_status = status
        self.response = response


class WaitExecutor:
    def __init__(self, transport, assertion_engine, *, clock=monotonic, sleeper=sleep):
        self.transport, self.assertions = transport, assertion_engine
        self.clock, self.sleeper = clock, sleeper

    def send(self, request, context, case, deadline=None):
        policy = case.wait_policy
        if policy and (not policy.contract_confirmed or policy.adapter_ref != "configured-state@1"):
            raise RequestStopped("wait_state_contract_missing", "blocked")
        if policy and (
            not policy.state_map
            or "succeeded" not in policy.state_map.values()
            or not all(
                math.isfinite(value)
                for value in [
                    policy.interval_seconds,
                    policy.deadline_seconds,
                    policy.max_interval_seconds,
                ]
            )
        ):
            raise RequestStopped("等待状态映射/预算不合法", "blocked")
        safe_query = (
            case.metadata.get("operation_kind") == "query"
            and case.metadata.get("query_contract_confirmed") is True
        )
        if policy and not safe_query:
            raise RequestStopped("wait只能查询已确认无副作用接口", "blocked")
        retries = policy.network_retries if policy else case.metadata.get("network_retries", 0)
        if retries and (
            not safe_query
            or not isinstance(retries, int)
            or isinstance(retries, bool)
            or not 0 <= retries <= 3
        ):
            raise RequestStopped("network_retries仅允许明确安全查询且最多3次", "blocked")
        if not policy and retries == 0:
            return self.transport.send(request, context, case)
        stop = context.plugin_state.get("execution", {}).get("should_stop")
        total_deadline = min(
            deadline or float("inf"),
            self.clock() + (policy.deadline_seconds if policy else request.timeout_seconds),
        )
        network = context.artifacts.setdefault("network_attempts", {}).setdefault(case.case_id, [])
        trace = context.artifacts.setdefault("poll_trace", {}).setdefault(case.case_id, [])

        def network_event(event):
            network.append(event)
            counts = context.artifacts.setdefault("network_attempt_count", {})
            counts[case.case_id] = counts.get(case.case_id, 0) + 1
            limit = policy.trace_limit if policy else 100
            if len(network) > limit:
                del network[1]

        previous = None
        last = None
        interval = policy.interval_seconds if policy else 0
        for attempt in range(1, (policy.max_attempts if policy else 1) + 1):
            if stop and stop():
                raise RequestStopped("等待被取消", "cancelled", last)
            if self.clock() >= total_deadline:
                raise RequestStopped("等待超过截止时间", "timed_out", last)
            for retry in range(retries + 1):
                if stop and stop():
                    raise RequestStopped("重试前已取消", "cancelled", last)
                remaining = total_deadline - self.clock()
                if remaining <= 0:
                    raise RequestStopped("查询预算用尽", "timed_out", last)
                request.timeout_seconds = min(request.timeout_seconds, remaining)
                started = self.clock()
                try:
                    execution = context.plugin_state.setdefault("execution", {})
                    previous_deadline = execution.get("request_deadline_monotonic")
                    execution["request_deadline_monotonic"] = total_deadline
                    try:
                        last = self.transport.send(request, context, case)
                    finally:
                        if previous_deadline is None:
                            execution.pop("request_deadline_monotonic", None)
                        else:
                            execution["request_deadline_monotonic"] = previous_deadline
                    network_event(
                        {
                            "attempt": attempt,
                            "retry": retry,
                            "status_code": last.status_code,
                            "elapsed_ms": (self.clock() - started) * 1000,
                        }
                    )
                    break
                except (ConnectionError, TimeoutError, OSError) as exc:
                    network_event(
                        {
                            "attempt": attempt,
                            "retry": retry,
                            "error_type": type(exc).__name__,
                            "elapsed_ms": (self.clock() - started) * 1000,
                        }
                    )
                    if self.clock() >= total_deadline:
                        raise RequestStopped("网络调用耗尽等待预算", "timed_out", last) from exc
                    if retry == retries:
                        raise
                except Exception as exc:
                    # httpx异常可在最小环境按模块/基类识别，但断言/配置异常绝不重试。
                    try:
                        import httpx

                        transient = isinstance(exc, httpx.TransportError)
                    except ImportError:
                        transient = False
                    if not transient:
                        raise
                    network_event(
                        {
                            "attempt": attempt,
                            "retry": retry,
                            "error_type": type(exc).__name__,
                            "elapsed_ms": (self.clock() - started) * 1000,
                        }
                    )
                    if self.clock() >= total_deadline:
                        raise RequestStopped("网络调用耗尽等待预算", "timed_out", last) from exc
                    if retry == retries:
                        raise
            if not policy:
                return last
            if self.clock() >= total_deadline:
                raise RequestStopped("查询返回后预算已耗尽", "timed_out", last)
            raw = resolve_field_path(last.body, policy.state_selector)
            mapped = policy.state_map.get(str(raw))
            trace.append(
                {
                    "attempt": attempt,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "raw_state": raw,
                    "state": mapped or "unknown",
                    "adapter_ref": policy.adapter_ref,
                    "status_code": last.status_code,
                    "elapsed_ms": last.elapsed_ms,
                }
            )
            context.artifacts.setdefault("poll_attempts", {})[case.case_id] = attempt
            if len(trace) > policy.trace_limit:
                del trace[1]
            if (
                last.status_code >= 400
                or resolve_field_path(last.body, policy.success_code_path) != policy.success_code
            ):
                raise RequestStopped("轮询查询业务失败", "failed", last)
            if not has_field_path(last.body, policy.state_selector) or mapped not in {
                "pending",
                "running",
                "succeeded",
                "failed",
            }:
                raise RequestStopped("未知业务状态，不能推断成功", "error", last)
            if previous == "running" and mapped == "pending":
                raise RequestStopped("非法状态回退 running→pending", "error", last)
            previous = mapped
            if policy.failure_assertions:
                failure = self.assertions.evaluate_all(policy.failure_assertions, last, context)
                if any(item.status == ExecutionStatus.ERROR for item in failure):
                    raise RequestStopped("失败谓词配置错误", "error", last)
                if all(item.status == ExecutionStatus.PASSED for item in failure):
                    raise RequestStopped("失败谓词命中", "failed", last)
            if mapped == "failed":
                raise RequestStopped("异步任务进入失败终态", "failed", last)
            if mapped == "succeeded":
                checks = self.assertions.evaluate_all(policy.success_assertions, last, context)
                if any(item.status == ExecutionStatus.ERROR for item in checks):
                    raise RequestStopped("成功谓词配置错误", "error", last)
                if not all(item.status == ExecutionStatus.PASSED for item in checks):
                    raise RequestStopped("终态成功但业务谓词未满足", "failed", last)
                return last
            if attempt == policy.max_attempts:
                break
            delay = min(
                interval, policy.max_interval_seconds, max(0, total_deadline - self.clock())
            )
            # 小片等待保证取消可响应，不做无限sleep。
            while delay > 0:
                if stop and stop():
                    raise RequestStopped("等待间隔被取消", "cancelled", last)
                portion = min(delay, 0.1)
                self.sleeper(portion)
                delay -= portion
            interval = min(interval * policy.backoff, policy.max_interval_seconds)
        raise RequestStopped("等待达到最大次数", "timed_out", last)

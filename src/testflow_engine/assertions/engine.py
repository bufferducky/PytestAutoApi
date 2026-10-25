"""
断言执行骨架。

当前版本只做三件事：
1. 根据 selector/source 从响应或上下文中取值。
2. 执行有限但常用的断言操作。
3. 产出统一的 AssertionResult，交给报告层继续聚合。

后续若引入表达式脚本、数据库断言、快照断言，可以继续在这里扩展。
"""

import json
import math
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Any

from .._field_path import has_field_path, resolve_field_path
from ..models import (
    AssertionOperator,
    AssertionResult,
    AssertionSource,
    AssertionSpec,
    ExecutionContext,
    ExecutionStatus,
    ResponseSnapshot,
    SelectorType,
)
from .business import BUILTIN_RULES, CUSTOM_RULES, keyed, normalize, schema_matches, type_matches

try:
    from jsonpath import jsonpath as jsonpath_extract
except ImportError:  # pragma: no cover - 兼容最小环境
    jsonpath_extract = None


class AssertionEngine:
    """执行标准化断言定义。"""

    def evaluate_all(
        self,
        assertions: list[AssertionSpec],
        response: ResponseSnapshot,
        context: ExecutionContext,
    ) -> list[AssertionResult]:
        """逐条执行断言，并保留每条断言的详细结果。"""

        results = []
        for assertion in assertions:
            results.append(self.evaluate(assertion=assertion, response=response, context=context))
        return results

    def evaluate(
        self,
        assertion: AssertionSpec,
        response: ResponseSnapshot,
        context: ExecutionContext,
    ) -> AssertionResult:
        """执行单条断言。"""

        actual, expected, missing = None, assertion.expected, False
        try:
            expected = (
                self._context_ref(context, assertion.expected_ref)
                if assertion.expected_ref
                else assertion.expected
            )
            source = (
                response.headers
                if assertion.source == AssertionSource.RESPONSE_HEADERS
                else context.variables
                if assertion.source == AssertionSource.CONTEXT
                else response.body
            )
            if assertion.source != AssertionSource.STATUS_CODE:
                selector = assertion.selector
                if (
                    assertion.selector_type == SelectorType.JSONPATH
                    and selector.startswith("$.")
                    and not any(x in selector for x in ["*", "?", ".."])
                ):
                    selector = selector[2:].replace("[", ".").replace("]", "")
                missing = bool(selector) and not has_field_path(source, selector)
                if assertion.selector_type == SelectorType.JSONPATH and any(
                    x in selector for x in ["*", "?", ".."]
                ):
                    missing = False
            actual = self._resolve_actual(assertion, response, context)
            if assertion.selector_type == SelectorType.JSONPATH and any(
                x in assertion.selector for x in ["*", "?", ".."]
            ):
                if jsonpath_extract is None:
                    raise ValueError("复杂JSONPath需要jsonpath依赖，不能猜测结果")
                missing = jsonpath_extract(source, assertion.selector) is False
            if not math.isfinite(assertion.tolerance):
                raise ValueError("tolerance必须有限")
            for value in [actual, expected]:
                if isinstance(value, (float, Decimal)) and not math.isfinite(value):
                    raise ValueError("断言值不能为NaN/Infinity")
            if assertion.select_by:
                selection = assertion.select_by
                wanted = (
                    self._context_ref(context, selection["value_ref"])
                    if selection.get("value_ref")
                    else selection.get("value")
                )
                if not isinstance(actual, list):
                    raise ValueError("精确对象选择需要数组")
                matches = [
                    item
                    for item in actual
                    if isinstance(item, dict)
                    and resolve_field_path(item, selection["key"]) == wanted
                ]
                if len(matches) != 1:
                    raise ValueError("目标对象缺失或不唯一，不能取首条")
                if selection.get("field") and not has_field_path(matches[0], selection["field"]):
                    raise ValueError("目标对象字段缺失")
                actual = resolve_field_path(matches[0], selection.get("field", ""))
                missing = False
            if missing and assertion.operator not in {
                AssertionOperator.IS_MISSING,
                AssertionOperator.EXISTS,
            }:
                raise ValueError("断言字段缺失: " + assertion.selector)
            if assertion.rule_ref in CUSTOM_RULES:
                callback, reads = CUSTOM_RULES[assertion.rule_ref]
                inputs = {ref: deepcopy(self._context_ref(context, ref)) for ref in reads}
                outcome = callback(actual=actual, expected=expected, inputs=inputs)
                if not isinstance(outcome, bool):
                    raise ValueError("规则插件须返回bool")
                return AssertionResult(
                    name=assertion.name,
                    status=ExecutionStatus.PASSED if outcome else ExecutionStatus.FAILED,
                    actual=actual,
                    expected=expected,
                    message=assertion.message or "受控业务规则比较",
                    rule_version=assertion.rule_ref,
                    source_ref=assertion.source.value + ":" + assertion.selector,
                    actual_missing=missing,
                )
            if assertion.operator == AssertionOperator.IS_MISSING:
                passed = missing
            elif assertion.operator == AssertionOperator.EXISTS:
                passed = not missing
            elif missing:
                raise ValueError("断言字段缺失: " + assertion.selector)
            elif assertion.operator == AssertionOperator.IS_NULL:
                passed = actual is None
            else:
                if assertion.rule_ref:
                    if assertion.rule_ref not in BUILTIN_RULES:
                        raise ValueError("不支持的规则版本: " + assertion.rule_ref)
                    baseline = (
                        self._context_ref(context, assertion.baseline_ref)
                        if assertion.baseline_ref
                        else None
                    )
                    if assertion.rule_ref == "count_delta@1":
                        if not isinstance(actual, (list, int)) or not isinstance(
                            baseline, (list, int)
                        ):
                            raise ValueError("count_delta须是精确对象的集合或计数")
                        actual = (len(actual) if isinstance(actual, list) else actual) - (
                            len(baseline) if isinstance(baseline, list) else baseline
                        )
                    elif assertion.rule_ref == "unchanged@1":
                        expected = baseline
                actual_value = normalize(actual, assertion.value_type, assertion.normalization)
                expected_value = normalize(expected, assertion.value_type, assertion.normalization)
                if (
                    assertion.operator == AssertionOperator.EQUALS
                    and assertion.value_type != "native"
                ):
                    difference = abs(actual_value - expected_value)
                    if isinstance(actual_value, datetime):
                        difference = difference.total_seconds()
                    passed = (
                        difference <= Decimal(str(assertion.tolerance))
                        if isinstance(difference, Decimal)
                        else difference <= assertion.tolerance
                    )
                elif assertion.operator == AssertionOperator.TYPE_IS:
                    passed = type_matches(actual, expected)
                elif assertion.operator == AssertionOperator.SCHEMA:
                    passed = schema_matches(actual, expected)
                elif assertion.operator in {
                    AssertionOperator.SET_EQUALS,
                    AssertionOperator.KEYED_EQUALS,
                    AssertionOperator.UNIQUE,
                }:
                    key = assertion.extras.get("key", "id")
                    if assertion.operator == AssertionOperator.KEYED_EQUALS:
                        passed = keyed(actual, key) == keyed(expected, key)
                    elif assertion.operator == AssertionOperator.UNIQUE:
                        if not isinstance(actual, list):
                            raise ValueError("unique需要数组")
                        passed = len(actual) == len(
                            set(json.dumps(item, sort_keys=True, default=str) for item in actual)
                        )
                    else:
                        passed = sorted(
                            json.dumps(item, sort_keys=True, default=str) for item in actual
                        ) == sorted(str(item) for item in expected)
                else:
                    passed = self._match(assertion.operator, actual_value, expected_value)
            status = ExecutionStatus.PASSED if passed else ExecutionStatus.FAILED
            message = (
                assertion.message or f"断言[{assertion.name}] 实际值={actual!r} 期望值={expected!r}"
            )
        except Exception as exc:
            status, message = ExecutionStatus.ERROR, str(exc)
        return AssertionResult(
            name=assertion.name,
            status=status,
            actual=actual,
            expected=expected,
            message=message,
            rule_version=assertion.rule_ref or "builtin@1",
            source_ref=assertion.source.value + ":" + assertion.selector,
            actual_missing=missing,
        )

    @staticmethod
    def _context_ref(context, reference):
        if not reference or not has_field_path(context.variables, reference):
            raise ValueError("断言上下文引用不存在: " + str(reference))
        return resolve_field_path(context.variables, reference)

    def _resolve_actual(
        self,
        assertion: AssertionSpec,
        response: ResponseSnapshot,
        context: ExecutionContext,
    ) -> Any:
        """根据断言配置解析实际值。"""

        if assertion.source == AssertionSource.STATUS_CODE:
            return response.status_code
        if assertion.source == AssertionSource.RESPONSE_HEADERS:
            return self._extract_value(
                response.headers,
                assertion.selector,
                assertion.selector_type,
            )
        if assertion.source == AssertionSource.CONTEXT:
            return self._extract_value(
                context.variables,
                assertion.selector,
                assertion.selector_type,
            )
        return self._extract_value(
            response.body,
            assertion.selector,
            assertion.selector_type,
            response,
        )

    def _extract_value(
        self,
        source: Any,
        selector: str,
        selector_type: SelectorType,
        response: ResponseSnapshot = None,
    ) -> Any:
        """
        从目标对象里取值。

        这里特意保留 JSONPath 支持，是为了 legacy YAML 能先迁移到新骨架，
        再逐步迁移到平台内部更稳定的 field_path DSL。
        """

        if selector_type == SelectorType.STATUS_CODE and response is not None:
            return response.status_code
        if not selector:
            return source
        if selector_type == SelectorType.JSONPATH:
            return self._extract_jsonpath(source=source, selector=selector)
        return self._extract_field_path(source=source, selector=selector)

    @staticmethod
    def _extract_field_path(source: Any, selector: str) -> Any:
        """按 `data.token` 这样的点路径取值。"""

        return resolve_field_path(source=source, selector=selector)

    def _extract_jsonpath(self, source: Any, selector: str) -> Any:
        """
        优先走 jsonpath 库；若环境里没有该依赖，则退化为简单路径兼容。

        退化逻辑只能覆盖 `$.a.b.c` 这类简单路径，足够支撑骨架阶段的结构测试。
        """

        if jsonpath_extract is not None:
            values = jsonpath_extract(source, selector)
            if values is False:
                return None
            if isinstance(values, list) and len(values) == 1:
                return values[0]
            return values
        normalized = selector.replace("$.", "").replace("[", ".").replace("]", "")
        return self._extract_field_path(source=source, selector=normalized)

    @staticmethod
    def _match(operator: AssertionOperator, actual: Any, expected: Any) -> bool:
        """根据操作符比较 actual 和 expected。"""

        if operator == AssertionOperator.EQUALS:
            return actual == expected and (isinstance(actual, bool) == isinstance(expected, bool))
        if operator == AssertionOperator.NOT_EQUALS:
            return actual != expected
        if operator == AssertionOperator.NOT_CONTAINS:
            return actual is not None and expected not in actual
        if operator == AssertionOperator.CONTAINS:
            if actual is None:
                return False
            return expected in actual
        if operator == AssertionOperator.EXISTS:
            return actual is not None
        if operator == AssertionOperator.GREATER_THAN:
            return actual > expected
        if operator == AssertionOperator.GREATER_OR_EQUAL:
            return actual >= expected
        if operator == AssertionOperator.LESS_THAN:
            return actual < expected
        if operator == AssertionOperator.LESS_OR_EQUAL:
            return actual <= expected
        raise ValueError(f"不支持的断言操作: {operator}")

    @staticmethod
    def _build_default_message(assertion: AssertionSpec, actual: Any) -> str:
        """生成默认断言消息，方便报告层直接展示。"""

        return f"断言[{assertion.name}] 实际值={actual!r} 期望值={assertion.expected!r}"

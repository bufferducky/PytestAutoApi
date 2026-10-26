"""场景发布校验与编译；输出仍交给现有 TestFlowEngine。"""

import json
import math
import re
from copy import deepcopy

from pyta_platform_backend.schemas.assets import ScenarioDraft
from testflow_engine import TestCaseDefinition, TestRunDefinition
from testflow_engine.assertions.business import BUILTIN_RULES, CUSTOM_RULES

TEMPLATE = re.compile(r"{{\s*([^{}]+?)\s*}}")


def dump(model):
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def preflight(data):
    errors, warnings = [], []
    try:
        draft = ScenarioDraft(**data)
    except ValueError as exc:
        return {"valid": False, "errors": [{"path": "draft", "message": str(exc)}], "warnings": []}
    if draft.schema_version != 1:
        errors.append({"path": "schema_version", "message": "不支持的 schema_version"})
    if not draft.steps:
        errors.append({"path": "steps", "message": "场景步骤不能为空"})
    if draft.migration_blockers:
        errors.append(
            {"path": "migration_blockers", "message": "; ".join(draft.migration_blockers)}
        )
    fixture_names = set()
    for index, requirement in enumerate(draft.fixtures):
        if requirement.name in fixture_names or not re.fullmatch(
            r"[a-zA-Z_][\w-]*", requirement.name
        ):
            errors.append({"path": f"fixtures.{index}.name", "message": "fixture名称必须唯一稳定"})
        if any(dep not in fixture_names for dep in requirement.depends_on):
            errors.append(
                {"path": f"fixtures.{index}.depends_on", "message": "资源依赖须向前且无环"}
            )
        fixture_names.add(requirement.name)
    ids, available, main_ids = set(), set(), set()
    phases = {"setup": 0, "action": 1, "verify": 2, "cleanup": 3}
    previous_phase = 0
    for index, step in enumerate(draft.steps):
        path = f"steps.{index}"

        def issue(field, message, path=path):
            errors.append({"path": path + "." + field, "message": message})

        if not re.fullmatch(r"[a-zA-Z_][\w-]*", step.step_id) or step.step_id in ids:
            issue("step_id", "ID 必须唯一且为稳定标识")
        if step.type not in {"http", "wait_until"}:
            issue("type", "当前步骤类型未注册；fixture/wait 需后续能力，不能静默跳过")
        if step.type == "wait_until":
            if (
                step.wait_policy is None
                or not step.wait_policy.contract_confirmed
                or step.wait_policy.adapter_ref != "configured-state@1"
            ):
                issue("wait_policy", "等待需要已确认配置状态适配器")
            if step.operation_kind != "query" or not step.contract_confirmed:
                issue("operation_kind", "等待只能使用已确认无副作用查询")
            if step.wait_policy and not set(step.wait_policy.state_map.values()) <= {
                "pending",
                "running",
                "succeeded",
                "failed",
            }:
                issue("wait_policy", "未知通用状态")
        elif step.wait_policy is not None:
            issue("wait_policy", "wait_policy必须匹配wait_until类型")
        if step.wait_policy:
            policy = step.wait_policy
            if not policy.state_map or "succeeded" not in policy.state_map.values():
                issue("wait_policy.state_map", "必须显式映射成功终态")
            if not all(
                math.isfinite(v)
                for v in [
                    policy.interval_seconds,
                    policy.deadline_seconds,
                    policy.max_interval_seconds,
                ]
            ):
                issue("wait_policy", "等待预算/间隔必须有限")
            if not re.fullmatch(r"[\w-]+(?:\.[\w-]+)*", policy.state_selector):
                issue("wait_policy.state_selector", "无效状态字段路径")
        assertions = step.assertions + (
            step.wait_policy.success_assertions + step.wait_policy.failure_assertions
            if step.wait_policy
            else []
        )
        for assertion_index, assertion in enumerate(assertions):
            if (
                assertion.selector_type.value == "field_path"
                and assertion.selector
                and not re.fullmatch(r"[\w-]+(?:\.[\w-]+)*", assertion.selector)
            ):
                issue(f"assertions.{assertion_index}.selector", "无效字段路径")
            if assertion.rule_ref and assertion.rule_ref not in BUILTIN_RULES | set(CUSTOM_RULES):
                issue(f"assertions.{assertion_index}.rule_ref", "未知规则版本")
            if not math.isfinite(assertion.tolerance):
                issue(f"assertions.{assertion_index}.tolerance", "误差必须有限")
            if assertion.select_by and (
                not assertion.select_by.get("key")
                or not (assertion.select_by.get("value_ref") or "value" in assertion.select_by)
            ):
                issue(
                    f"assertions.{assertion_index}.select_by",
                    "精确对象选择须声明key与value/value_ref",
                )
            if assertion.value_type not in {"native", "decimal", "datetime"}:
                issue(f"assertions.{assertion_index}.value_type", "未知比较类型")
        for ref in step.plugin_refs:
            # 当前插件由 worker 按运行类型装配，没有逐步骤选择消费者。
            # 在实现选择语义前明确拒绝，避免合法字符串被编译静默丢弃。
            issue("plugin_refs", "当前不支持逐步骤插件选择: " + ref)
        if phases[step.phase] < previous_phase:
            issue("phase", "步骤须按准备、动作、验证、清理排序")
        previous_phase = phases[step.phase]
        for dependency in step.depends_on:
            if dependency not in ids or dependency == step.step_id:
                issue("depends_on", "依赖必须是前面的已声明步骤（禁止环/后向引用）")
        raw = json.dumps(dump(step.request), ensure_ascii=False, default=str)
        reads = set(TEMPLATE.findall(raw)) | set(step.reads)
        for assertion in assertions:
            reads.update(
                ref
                for ref in [
                    assertion.expected_ref,
                    assertion.baseline_ref,
                    assertion.select_by.get("value_ref"),
                ]
                if ref
            )
        for assertion in assertions:
            if assertion.rule_ref in CUSTOM_RULES:
                reads.update(CUSTOM_RULES[assertion.rule_ref][1])
        for selector in reads:
            namespace = selector.split(".")[0]
            if namespace == "outputs":
                if selector not in available:
                    issue("reads", "输出尚未声明: " + selector)
                producer = selector.split(".")[1] if "." in selector else ""
                if producer not in step.depends_on:
                    issue("depends_on", "读取输出必须显式依赖生产步骤: " + producer)
            elif namespace == "params":
                key = selector.split(".")[1] if "." in selector else ""
                if key not in draft.parameters_schema and key not in draft.parameters:
                    issue("reads", "未声明参数: " + selector)
            elif namespace not in {"host", "identity", "fixtures", "runtime"}:
                issue("reads", "不支持的变量命名空间: " + namespace)
            elif namespace == "fixtures":
                name = selector.split(".")[1] if "." in selector else ""
                if name not in fixture_names:
                    issue("reads", "fixture未声明: " + name)
        for extractor in step.extractors:
            if not extractor.target.startswith("outputs." + step.step_id + "."):
                issue("extractors", "提取仅能写 outputs.<step_id>.*")
            available.add(extractor.target)
        ids.add(step.step_id)
        if step.phase != "cleanup":
            main_ids.add(step.step_id)
    if not any(
        s.enabled and s.required and s.assertions and s.phase != "cleanup" for s in draft.steps
    ):
        errors.append({"path": "steps", "message": "至少一个必需主步骤须有有效断言"})
    return {"valid": not errors, "errors": errors, "warnings": warnings + draft.migration_warnings}


def parameters(draft, overrides):
    result = deepcopy(draft["parameters"])
    for key, value in overrides.items():
        if key not in draft["parameters_schema"]:
            raise ValueError("未声明/不可覆盖参数: " + key)
        result[key] = value
    kinds = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for key, rule in draft["parameters_schema"].items():
        if rule.get("required") and key not in result:
            raise ValueError("缺少参数: " + key)
        if key in result and rule.get("type"):
            expected = kinds.get(rule["type"])
            if (
                expected is None
                or not isinstance(result[key], expected)
                or isinstance(result[key], bool)
                and rule["type"] in {"integer", "number"}
            ):
                raise ValueError("参数类型错误: " + key)
    return result


def compile_scenario(published, *, scope_id="scenario", overrides=None):
    data = published["data"]
    check = preflight(data)
    if not check["valid"]:
        raise ValueError(json.dumps(check["errors"], ensure_ascii=False))
    cases, cleanups = [], []
    for step in data["steps"]:
        identifier = scope_id + "__" + step["step_id"]
        case = TestCaseDefinition(
            case_id=identifier,
            title=step["name"],
            request=step["request"],
            assertions=step["assertions"],
            extractors=step["extractors"],
            enabled=step["enabled"],
            required=step["required"],
            wait_policy=step.get("wait_policy"),
            depends_on=[scope_id + "__" + s for s in step["depends_on"]],
            metadata={
                **step["metadata"],
                "scope_id": scope_id,
                "operation_kind": step["operation_kind"],
                "safe_to_replay": step["safe_to_replay"],
                "query_contract_confirmed": step["contract_confirmed"]
                and step["operation_kind"] == "query",
                "scenario_ref": {
                    "id": published["id"],
                    "version": published["version"],
                    "hash": published["hash"],
                },
                "phase": step["phase"],
                "step_id": step["step_id"],
            },
        )
        (cleanups if step["phase"] == "cleanup" else cases).append(case)
    variables = {
        "params": parameters(data, overrides or {}),
        "outputs": {},
        "runtime": {},
        "fixtures": {},
    }
    return TestRunDefinition(
        name=data["name"],
        cases=cases,
        cleanup_cases=list(reversed(cleanups)),
        metadata={"scopes": {scope_id: variables}},
    )

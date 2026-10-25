"""创建与执行共用的预检；未知模式和空计划不能进入队列。"""

import json
import math
from pathlib import Path

from testflow_engine import LegacyYamlCompatLoader, TestRunDefinition

from .redaction import REDACTED


def validate_live_payload(payload):
    """新任务与消费共用边界；历史读取不调用此校验。"""
    if payload.get("transport_mode") != "live":
        raise ValueError("transport_mode 必须显式为 live；模拟执行已移除")
    if any(key.startswith("mock") for key in payload):
        raise ValueError("模拟响应参数已移除，不能提交 mock 参数")


def load_definition(payload):
    mode, transport = payload.get("execution_mode"), payload.get("transport_mode")
    if mode == "evaluation":
        raise ValueError("evaluation_execution_disabled: 新评估执行已禁用；历史报告仍可读取")
    validate_live_payload(payload)
    if mode == "ui_journey":
        from pyta_platform_backend.schemas.journeys import JourneyDefinition

        published = payload.get("journey_definition", {})
        JourneyDefinition(**published.get("data", {}))
        if transport != "live":
            raise ValueError("UI旅程不能用Mock假装设备执行")
        return None
    if mode not in {"standard_run", "legacy_yaml"}:
        raise ValueError("execution_mode 必须显式为 standard_run / legacy_yaml")
    for key, default in [
        ("timeout_seconds", 300),
        ("cleanup_timeout_seconds", 60),
        ("queue_timeout_seconds", 300),
    ]:
        value = payload.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} 必须是有限正数")
        if not math.isfinite(value) or value <= 0 or value > 86400:
            raise ValueError(f"{key} 必须在 (0, 86400] 内")
    if mode == "legacy_yaml":
        root = Path(__file__).resolve().parents[5]
        path = (root / str(payload.get("legacy_yaml_path", ""))).resolve()
        if not path.is_relative_to(root / "data") or not path.is_file():
            raise ValueError("legacy_yaml_path 必须是 data 内存在的 YAML 文件")
        loader = LegacyYamlCompatLoader()
        definition = loader.to_run_definition(
            loader.load_from_path(str(path)), run_name=f"legacy:{path.name}"
        )
        definition.variables.update(payload.get("variables", {}))
    else:
        definition = TestRunDefinition(**payload.get("run_definition", {}))
    if not definition.cases:
        raise ValueError("run_definition.cases 不能为空")
    cases = definition.cases + definition.cleanup_cases
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case_id 必须唯一（包括清理步骤）")
    for case in cases:
        if not math.isfinite(case.request.timeout_seconds) or case.request.timeout_seconds <= 0:
            raise ValueError(f"{case.case_id}: request.timeout_seconds 必须是有限正数")
    # 公开快照中的占位不是可重放凭证；R02 的 secret provider 将负责引用解析。
    dump = definition.model_dump() if hasattr(definition, "model_dump") else definition.dict()
    if REDACTED in json.dumps(dump, default=str):
        raise ValueError("快照含已脱敏凭证，需重新配置引用，不能重放占位值")
    return definition

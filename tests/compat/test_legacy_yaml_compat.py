from pathlib import Path

from testflow_engine import (
    BodyType,
    CallableTransport,
    LegacyCachePlugin,
    LegacyYamlCompatLoader,
    ResponseSnapshot,
    SelectorType,
)
from testflow_engine import (
    TestFlowEngine as FlowEngine,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "legacy_yaml"


def test_legacy_yaml_document_can_convert_to_standard_run_definition():
    """验证 legacy YAML 至少能被桥接到新标准模型。"""

    raw_document = {
        "case_common": {
            "host": "https://example.test",
            "allureEpic": "开发平台接口",
            "allureFeature": "登录模块",
            "allureStory": "登录",
        },
        "login_success": {
            "detail": "用户登录成功",
            "method": "POST",
            "url": "/api/login",
            "headers": {"X-Trace-Id": "trace-001"},
            "requestType": "JSON",
            "data": {"username": "demo", "password": "secret"},
            "assert": [
                {
                    "jsonpath": "$.code",
                    "type": "==",
                    "value": 0,
                    "AssertType": "json",
                }
            ],
            "is_run": True,
        },
    }

    loader = LegacyYamlCompatLoader()
    document = loader.load_from_dict(
        payload=raw_document,
        source_path="uploaded-login.yaml",
    )
    run_definition = loader.to_run_definition(document)
    case = run_definition.cases[0]

    assert document.source_path == "uploaded-login.yaml"
    assert case.source.kind == "legacy_yaml"
    assert case.request.url == "https://example.test/api/login"
    assert case.request.body_type == BodyType.JSON
    assert case.tags == ["开发平台接口", "登录模块", "登录"]
    assert case.assertions[0].selector == "$.code"
    assert case.assertions[0].selector_type == SelectorType.JSONPATH


def test_legacy_login_shape_can_be_loaded_from_fixture():
    """用合成文件验证旧 YAML 字段形态与文件读取，不依赖旧业务用例。"""

    loader = LegacyYamlCompatLoader()
    document = loader.load_from_path(str(FIXTURES / "login.yaml"))
    run_definition = loader.to_run_definition(document, run_name="fixture-login-yaml")

    assert run_definition.name == "fixture-login-yaml"
    assert len(run_definition.cases) == 3

    first_case = run_definition.cases[0]
    assert first_case.case_id == "login_01"
    assert first_case.title == "正常登录"
    assert first_case.enabled is True
    assert first_case.request.body_type == BodyType.JSON
    assert first_case.request.url == "{{host}}/api/login"
    assert first_case.assertions[0].name == "code"
    assert first_case.assertions[0].selector == "$.code"
    assert first_case.request.extras["legacy_dependence_case"] is False


def test_cache_yaml_shape_keeps_unmigrated_fields_in_request_extras():
    """更复杂的历史 YAML 字段先保存在 extras，避免迁移时静默丢失。"""

    loader = LegacyYamlCompatLoader()
    document = loader.load_from_path(str(FIXTURES / "cache_flow.yaml"))
    run_definition = loader.to_run_definition(document, run_name="cache-flow")

    first_case = run_definition.cases[0]
    assert first_case.case_id == "flow_01_resources"
    assert first_case.enabled is True
    assert first_case.request.body_type == BodyType.NONE
    assert (
        run_definition.cases[2].request.url
        == "{{host}}/details?id={{cache.option_id}}"
    )
    assert (
        run_definition.cases[4].request.body["optionId"]
        == "{{cache.option_id}}"
    )
    assert run_definition.cases[4].request.body["id"] == "{{cache.resource_id}}"
    assert first_case.request.extras["legacy_current_request_set_cache"] == [
        {
            "type": "response",
            "jsonpath": "$.data.records[0].id",
            "name": "resource_id",
        }
    ]

    skipped_case = next(
        case
        for case in run_definition.cases
        if case.case_id == "flow_04_select_default"
    )
    assert skipped_case.enabled is False


def test_cache_yaml_can_execute_with_legacy_cache_plugin():
    """合成依赖流程应能通过 cache 兼容插件跑通。

    这个测试比 shape test 更进一步：
    它证明 `$cache{...}` 不只是被转换成占位符，
    而是真的能在执行链路里由前序响应写回上下文，再被后续 case 使用。
    """

    loader = LegacyYamlCompatLoader()
    document = loader.load_from_path(str(FIXTURES / "cache_flow.yaml"))
    run_definition = loader.to_run_definition(document, run_name="cache-flow-exec")
    if hasattr(run_definition, "model_copy"):
        run_definition = run_definition.model_copy(
            update={
                "variables": {
                    "host": "https://example.test",
                }
            },
            deep=True,
        )
    else:
        run_definition = run_definition.copy(
            update={
                "variables": {
                    "host": "https://example.test",
                }
            },
            deep=True,
        )

    response_map = {
        "flow_01_resources": ResponseSnapshot(
            status_code=200,
            body={"code": 200, "data": {"records": [{"id": "resource-001"}]}},
        ),
        "flow_02_options": ResponseSnapshot(
            status_code=200,
            body={"code": 200, "data": [{"id": "option-001"}]},
        ),
    }

    engine = FlowEngine(
        transport=CallableTransport(
            lambda request, context, case: response_map.get(
                case.case_id,
                ResponseSnapshot(status_code=200, body={"code": 200, "message": "ok"}),
            )
        ),
        plugins=[LegacyCachePlugin()],
    )
    result = engine.execute_run(run_definition)

    assert result.status == "passed"
    assert result.summary.total == 7
    assert result.summary.passed == 6
    assert result.summary.skipped == 1

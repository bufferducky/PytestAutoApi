"""
测试引擎核心数据模型。

这批模型是新引擎的第一层稳定边界，主要解决三个问题：
1. 平台主真源如何描述一个“可执行用例”。
2. 执行器、断言器、插件之间如何传递上下文。
3. 报告层如何拿到统一结果，而不再依赖 legacy YAML 的临时字段。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class HttpMethod(str, Enum):
    """HTTP 方法枚举。"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class BodyType(str, Enum):
    """
    请求体类型。

    这里保留了旧框架 requestType 的常见取值，方便 compatibility 层直接映射。
    """

    JSON = "json"
    FORM = "form"
    QUERY = "query"
    FILE = "file"
    RAW = "raw"
    NONE = "none"


class SelectorType(str, Enum):
    """
    断言取值方式。

    - field_path: 适合平台结构化 DSL，直接按 `data.token` 取值。
    - jsonpath: 兼容 legacy YAML 中已经存在的大量 JSONPath 写法。
    - status_code: 不从 body 取值，直接读取响应状态码。
    """

    FIELD_PATH = "field_path"
    JSONPATH = "jsonpath"
    STATUS_CODE = "status_code"


class AssertionSource(str, Enum):
    """断言读取的数据源。"""

    RESPONSE_BODY = "response_body"
    RESPONSE_HEADERS = "response_headers"
    STATUS_CODE = "status_code"
    CONTEXT = "context"


class AssertionOperator(str, Enum):
    """骨架阶段先内建最常用的一组断言操作。"""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    EXISTS = "exists"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    NOT_CONTAINS = "not_contains"
    IS_NULL = "is_null"
    IS_MISSING = "is_missing"
    TYPE_IS = "type_is"
    SCHEMA = "schema"
    SET_EQUALS = "set_equals"
    KEYED_EQUALS = "keyed_equals"
    UNIQUE = "unique"


class ExtractionSource(str, Enum):
    """变量提取的数据源。"""

    RESPONSE_BODY = "response_body"
    RESPONSE_HEADERS = "response_headers"
    STATUS_CODE = "status_code"


class ExecutionStatus(str, Enum):
    """执行状态统一枚举，报告层和调度层都使用这一组值。"""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CaseSource(BaseModel):
    """
    记录用例来自哪里。

    新平台的用例会来自数据库/接口配置，legacy 过来的用例则会带上 yaml 路径。
    """

    kind: str = "platform"
    path: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RequestSpec(BaseModel):
    """
    请求定义。

    这层只描述“要发什么请求”，不负责真正发送请求。
    执行器会把它交给 TransportAdapter，从而把 HTTP、Mock、录制回放解耦。
    """

    method: HttpMethod = HttpMethod.GET
    url: str
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    body_type: BodyType = BodyType.JSON
    body: Any = None
    timeout_seconds: float = 30.0
    extras: dict[str, Any] = Field(default_factory=dict)


class AssertionSpec(BaseModel):
    """
    单条断言定义。

    设计重点：
    - selector/selector_type 负责“怎么取值”
    - source 负责“从哪里取值”
    - operator/expected 负责“如何比较”
    """

    name: str
    selector: str = ""
    selector_type: SelectorType = SelectorType.FIELD_PATH
    source: AssertionSource = AssertionSource.RESPONSE_BODY
    operator: AssertionOperator = AssertionOperator.EQUALS
    expected: Any = None
    expected_ref: Optional[str] = None
    baseline_ref: Optional[str] = None
    value_type: str = "native"
    tolerance: float = Field(0, ge=0)
    normalization: dict[str, Any] = Field(default_factory=dict)
    select_by: dict[str, Any] = Field(default_factory=dict)
    rule_ref: Optional[str] = None
    message: Optional[str] = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ExtractionSpec(BaseModel):
    """
    标准化变量提取定义。

    它解决的是“前一个请求返回了什么值，后面的请求怎样继续使用它”。
    这是新架构里对旧 `current_request_set_cache` 的正式替代。
    """

    name: str
    selector: str
    selector_type: SelectorType = SelectorType.FIELD_PATH
    source: ExtractionSource = ExtractionSource.RESPONSE_BODY
    target: str = ""
    required: bool = True
    message: Optional[str] = None
    extras: dict[str, Any] = Field(default_factory=dict)


class WaitPolicy(BaseModel):
    adapter_ref: str = "configured-state@1"
    contract_confirmed: bool = False
    state_selector: str
    state_map: dict[str, str]
    success_code_path: str = "code"
    success_code: int = 200
    interval_seconds: float = Field(2, ge=0)
    backoff: float = Field(1, ge=1, le=5)
    max_interval_seconds: float = Field(10, gt=0)
    deadline_seconds: float = Field(60, gt=0, le=86400)
    max_attempts: int = Field(30, ge=1, le=10000)
    network_retries: int = Field(0, ge=0, le=3)
    trace_limit: int = Field(100, ge=2, le=1000)
    success_assertions: list[AssertionSpec] = Field(default_factory=list)
    failure_assertions: list[AssertionSpec] = Field(default_factory=list)


class TestCaseDefinition(BaseModel):
    """
    平台内的标准化用例模型。

    旧 YAML 和未来平台 DSL 都应该先转换到这里，再交给执行器。
    这样执行链路只需要维护一套运行逻辑。
    """

    case_id: str
    title: str
    request: RequestSpec
    depends_on: list[str] = Field(default_factory=list)
    wait_policy: Optional[WaitPolicy] = None
    required: bool = True
    assertions: list[AssertionSpec] = Field(default_factory=list)
    extractors: list[ExtractionSpec] = Field(default_factory=list)
    description: str = ""
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: CaseSource = Field(default_factory=CaseSource)


class TestRunDefinition(BaseModel):
    """
    一次执行任务的定义。

    worker/调度只需要关心 run，而执行器内部再拆成多个 case。
    """

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = "unnamed-run"
    cases: list[TestCaseDefinition] = Field(default_factory=list)
    cleanup_cases: list[TestCaseDefinition] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResponseSnapshot(BaseModel):
    """
    传输层返回的标准响应快照。

    这里故意不绑定 requests.Response，避免上层被第三方库对象拖住。
    """

    status_code: int
    headers: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    elapsed_ms: float = 0.0
    request_id: Optional[str] = None


class AssertionResult(BaseModel):
    """单条断言的执行结果。"""

    name: str
    status: ExecutionStatus
    actual: Any = None
    expected: Any = None
    message: str = ""
    rule_version: str = "builtin@1"
    source_ref: str = ""
    actual_missing: bool = False


class StepExecutionResult(BaseModel):
    """
    单步执行结果。

    当前骨架只有“请求执行”这一步，后续可扩展为前置脚本、变量装配、清理步骤等。
    """

    name: str
    status: ExecutionStatus
    response: Optional[ResponseSnapshot] = None
    request: Optional[RequestSpec] = None
    request_sent: bool = False
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    poll_trace: list[dict[str, Any]] = Field(default_factory=list)
    poll_attempts: int = 0
    network_attempts: list[dict[str, Any]] = Field(default_factory=list)
    network_attempt_count: int = 0
    http_attempt_count: int = 0
    http_replay_count: int = 0
    error_type: Optional[str] = None
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: Optional[str] = None
    started_at: datetime
    finished_at: datetime


class CaseExecutionResult(BaseModel):
    """单个用例的执行结果。"""

    case_id: str
    title: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ExecutionStatus
    steps: list[StepExecutionResult] = Field(default_factory=list)
    error: Optional[str] = None
    started_at: datetime
    finished_at: datetime


class ReportSummary(BaseModel):
    """报告摘要。"""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    blocked: int = 0
    requests: int = 0
    assertions: int = 0


class RunExecutionResult(BaseModel):
    """整次 run 的聚合结果。"""

    run_id: str
    name: str
    status: ExecutionStatus
    cases: list[CaseExecutionResult] = Field(default_factory=list)
    summary: ReportSummary = Field(default_factory=ReportSummary)
    error: Optional[str] = None
    cleanup_status: str = "not_started"
    authentication_results: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime


class ExecutionContext(BaseModel):
    """
    运行时上下文。

    这是执行器、插件、报告器之间共享的“内存工作台”：
    - variables: 平台下发变量、运行中间变量、插件写回变量
    - artifacts: 报告附件、原始响应、调试产物
    - plugin_state: 每个插件自己的运行状态
    """

    run_id: str
    variables: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    plugin_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    legacy_documents: list[str] = Field(default_factory=list)

    def set_variable(self, key: str, value: Any) -> None:
        """写入运行变量。"""

        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """读取运行变量。"""

        return self.variables.get(key, default)

    def remember_artifact(self, key: str, value: Any) -> None:
        """登记报告或调试工件。"""

        self.artifacts[key] = value

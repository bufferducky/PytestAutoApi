"""平台场景与套件资产。草稿宽容未知类型，发布必须通过编译。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from pyta_platform_backend.schemas.context import PublicModel
from pyta_platform_backend.schemas.resources import FixtureRequirement
from testflow_engine import AssertionSpec, ExtractionSpec, RequestSpec
from testflow_engine.models.core import WaitPolicy


class ScenarioStep(PublicModel):
    step_id: str = Field(..., min_length=1)
    name: str
    type: str = "http"
    phase: Literal["setup", "action", "verify", "cleanup"] = "verify"
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    enabled: bool = True
    operation_kind: Literal["query", "write"] = "query"
    contract_confirmed: bool = False
    safe_to_replay: bool = False
    request: RequestSpec
    wait_policy: Optional[WaitPolicy] = None
    assertions: list[AssertionSpec] = Field(default_factory=list)
    extractors: list[ExtractionSpec] = Field(default_factory=list)
    reads: list[str] = Field(default_factory=list)
    plugin_refs: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ScenarioDraft(PublicModel):
    schema_version: int = 1
    name: str = Field(..., min_length=1)
    module: str = "未分类"
    priority: Literal["P0", "P1", "P2"] = "P1"
    target_ref: str
    identity_ref: Optional[str] = None
    identity_binding_ref: Optional[str] = None
    parameters_schema: dict = Field(default_factory=dict)
    parameters: dict = Field(default_factory=dict)
    steps: list[ScenarioStep] = Field(default_factory=list)
    fixtures: list[FixtureRequirement] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source: dict = Field(default_factory=dict)
    migration_warnings: list[str] = Field(default_factory=list)
    migration_blockers: list[str] = Field(default_factory=list)


class ScenarioReference(PublicModel):
    scenario_id: str
    version: int = Field(..., ge=1)


class SuiteDraft(PublicModel):
    name: str = Field(..., min_length=1)
    scenarios: list[ScenarioReference] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    priority: Literal["P0", "P1", "P2"] = "P1"
    timeout_seconds: float = Field(300, gt=0, le=86400)


class SaveDraftRequest(BaseModel):
    expected_revision: int
    draft: dict


class PublishRequest(PublicModel):
    expected_revision: int
    change_note: str = Field(..., min_length=1)
    author: str = "platform-user"


class AssetRunRequest(PublicModel):
    build: str = "unspecified"
    transport_mode: Literal["live"]
    environment_id: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    requested_by: str = "platform-user"

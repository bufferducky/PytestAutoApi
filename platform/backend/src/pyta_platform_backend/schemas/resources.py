"""版本化fixture与明确资源策略；没有任意Python/SQL执行入口。"""

from typing import Literal, Optional

from pydantic import Field

from pyta_platform_backend.schemas.context import PublicModel
from testflow_engine import RequestSpec


class FixtureDefinition(PublicModel):
    name: str
    provider_ref: Literal["http-resource@1"] = "http-resource@1"
    strategy: Literal["create", "lease", "read_only"]
    contract_confirmed: bool = False
    acquire_request: Optional[RequestSpec] = None
    release_request: Optional[RequestSpec] = None
    snapshot_request: Optional[RequestSpec] = None
    id_path: str = "data.id"
    success_code_path: str = "code"
    success_code: int = 200
    already_absent_codes: list[int] = Field(default_factory=list)
    pool_id: Optional[str] = None
    object_id: Optional[str] = None
    restore_required: bool = True
    lease_seconds: int = Field(300, gt=0, le=86400)


class FixtureRequirement(PublicModel):
    name: str
    definition_id: str
    version: int = Field(..., ge=1)
    depends_on: list[str] = Field(default_factory=list)


class PoolResource(PublicModel):
    pool_id: str
    object_id: str
    target_id: str
    tenant_id: str = ""
    project_id: str = ""
    dedicated_test_resource: bool = False


class MediaManifest(PublicModel):
    name: str
    path: str
    sha256: str
    byte_size: int = Field(..., gt=0)
    duration_seconds: float = Field(..., gt=0)
    format: Literal["wav", "mp3"]
    language: str
    noise: str
    source: str
    authorized: bool = False
    redacted: bool = False
    applicable_scenarios: list[str] = Field(default_factory=list)

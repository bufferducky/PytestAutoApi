"""UI旅程独立于HTTP传输；只支持语义定位与有界动作。"""

from typing import Literal, Optional

from pydantic import Field

from pyta_platform_backend.schemas.context import PublicModel
from pyta_platform_backend.schemas.resources import FixtureRequirement
from testflow_engine import AssertionSpec, RequestSpec


class Selector(PublicModel):
    strategy: Literal["role", "label", "testid", "accessibility_id", "resource_id"]
    value: str
    name: Optional[str] = None


class JourneyAction(PublicModel):
    step_id: str
    name: str
    action: Literal[
        "navigate",
        "click",
        "fill",
        "assert_text",
        "assert_visible",
        "background",
        "permission",
        "api_assert",
    ]
    selector: Optional[Selector] = None
    value: Optional[str] = None
    value_ref: Optional[str] = None
    path: Optional[str] = None
    timeout_seconds: float = Field(10, gt=0, le=60)
    request: Optional[RequestSpec] = None
    assertions: list[AssertionSpec] = Field(default_factory=list)
    operation_kind: Literal["query", "write"] = "query"
    permission: Optional[str] = None
    permission_granted: Optional[bool] = None
    restore_permission_granted: Optional[bool] = None


class DeviceProfile(PublicModel):
    name: str
    device_secret_ref: str
    platform_version: str
    app_package: str = "com.yanjiai.app.new"
    app_activity: str = "io.dcloud.PandoraEntry"
    app_build_sha256: str
    installed_build_version: str
    appium_url: str = "http://127.0.0.1:4723"
    media_capabilities: list[str] = Field(default_factory=list)
    free_space_min_bytes: int = Field(100 * 1024 * 1024, ge=0)


class JourneyDefinition(PublicModel):
    name: str
    runner_type: Literal["web", "android"]
    runner_version: str = "ui-runner@1"
    target_ref: str
    identity_ref: Optional[str] = None
    identity_binding_ref: Optional[str] = None
    device_profile_id: Optional[str] = None
    device_profile_version: Optional[int] = None
    chromium_version: Optional[str] = None
    contract_confirmed: bool = False
    synthetic_test_data: bool = False
    capture_trace: bool = False
    capture_video: bool = False
    actions: list[JourneyAction] = Field(default_factory=list)
    fixtures: list[FixtureRequirement] = Field(default_factory=list)
    timeout_seconds: float = Field(300, gt=0, le=3600)
    risk_id: Optional[str] = None
    required_media_capabilities: list[str] = Field(default_factory=list)


class JourneyRunRequest(PublicModel):
    build: str = "unspecified"
    transport_mode: Literal["live"] = "live"

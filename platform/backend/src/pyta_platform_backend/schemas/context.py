"""公开上下文配置；凭证只有 env:PYTA_SECRET_* 引用，不接收原值。"""

from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class PublicModel(BaseModel):
    class Config:
        extra = "forbid"


class LoginStrategy(PublicModel):
    mode: Literal["none", "password"] = "none"
    contract_confirmed: bool = False
    login_path: str = "/api/v1/user/password_login"
    request_mode: Literal["json", "form"] = "json"
    username_field: str = "username"
    password_field: str = "password"
    password_transform: Literal["none", "md5"] = "none"
    token_path: str = "data.token"
    success_code_path: str = "code"
    success_code: int = 200
    header_name: str = "Authorization"
    header_template: Literal["{token}", "Bearer {token}"] = "{token}"
    expiry_path: Optional[str] = None
    expiry_format: Literal["epoch_seconds", "epoch_milliseconds", "relative_seconds"] = (
        "epoch_seconds"
    )
    unauthorized_business_code: int = 401
    timeout_seconds: float = Field(5, gt=0, le=30)


class ContextCheck(PublicModel):
    name: str
    path: str
    method: Literal["GET", "POST"] = "GET"
    query_contract_confirmed: bool = False
    body: dict = Field(default_factory=dict)
    success_code_path: str = "code"
    success_code: int = 200
    tenant_path: Optional[str] = None
    project_path: Optional[str] = None


class Profile(PublicModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(..., min_length=1)
    revision: int = Field(1, ge=1)


class TargetProfile(Profile):
    environment_id: str
    kind: Literal["center", "saas", "app", "practice", "default"] = "default"
    base_url: str
    requires_context: bool = False
    allowed_upload_origins: list[str] = Field(default_factory=list)
    auth: LoginStrategy = Field(default_factory=LoginStrategy)
    checks: list[ContextCheck] = Field(default_factory=list)


class IdentityProfile(Profile):
    target_ids: list[str] = Field(..., min_length=1)
    role_description: str = ""
    username_secret_ref: str
    password_secret_ref: str


class ContextBinding(Profile):
    target_id: str
    identity_id: str
    tenant_id: str = Field(..., min_length=1)
    project_id: str = Field(..., min_length=1)


class PreflightRequest(PublicModel):
    target_id: str
    identity_id: Optional[str] = None
    context_binding_id: Optional[str] = None
    execute_login: bool = False

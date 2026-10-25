"""固定套件版本、明确时区与错过策略。"""

from typing import Literal

from pydantic import Field

from pyta_platform_backend.schemas.context import PublicModel


class ScheduleDefinition(PublicModel):
    name: str
    suite_id: str
    suite_version: int = Field(..., ge=1)
    environment_id: str
    transport_mode: Literal["live"]
    cron: str
    timezone: str = "Asia/Shanghai"
    missed_policy: Literal["skip", "fire_once"] = "skip"
    busy_policy: Literal["queue", "skip"] = "queue"
    status: Literal["active", "paused"] = "paused"
    queue_timeout_seconds: int = Field(300, gt=0, le=86400)
    timeout_seconds: int = Field(300, gt=0, le=86400)
    parameters: dict = Field(default_factory=dict)
    concurrency_keys: list[str] = Field(default_factory=list)

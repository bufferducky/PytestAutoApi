"""平台后端配置定义。"""

import os
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy.engine import URL, make_url


class BackendSettings(BaseModel):
    """后端服务的最小配置集合。

    第一阶段只保留骨架真正需要的字段：
    1. FastAPI 应用标题、版本和 API 前缀
    2. worker 投递通道标识
    3. 轻量 scheduler 的轮询周期
    """

    app_name: str = "PytestAutoApi Platform Backend"
    app_version: str = "0.1.0"
    app_env: str = "dev"
    debug: bool = False
    api_prefix: str = "/api/v1"
    run_dispatch_channel: str = "memory-worker"
    scheduler_poll_interval_seconds: int = 30
    state_db_path: str = ""
    database_url: str = ""
    artifact_root: str = ""

    @classmethod
    def _field_default(cls, field_name: str):
        """读取字段默认值，兼容 Pydantic v1/v2。

        review 已经指出当前仓库环境可能同时出现 v1 和 v2，
        所以这里不再把默认值读取逻辑写死在某一版实现上。
        """

        if hasattr(cls, "model_fields"):
            return cls.model_fields[field_name].default
        return cls.__fields__[field_name].default

    @classmethod
    def from_env(cls) -> "BackendSettings":
        """从环境变量构造配置。

        这里先不用更重的 settings 框架，避免在骨架阶段引入额外依赖。
        等平台需要更复杂的配置来源时，再替换成专门的配置模块即可。
        """

        raw_values: dict[str, object] = {
            "app_name": os.getenv(
                "PLATFORM_BACKEND_APP_NAME",
                cls._field_default("app_name"),
            ),
            "app_version": os.getenv(
                "PLATFORM_BACKEND_APP_VERSION",
                cls._field_default("app_version"),
            ),
            "app_env": os.getenv("PLATFORM_BACKEND_APP_ENV", cls._field_default("app_env")),
            "debug": cls._read_bool(
                os.getenv("PLATFORM_BACKEND_DEBUG"),
                default=cls._field_default("debug"),
            ),
            "api_prefix": os.getenv(
                "PLATFORM_BACKEND_API_PREFIX",
                cls._field_default("api_prefix"),
            ),
            "run_dispatch_channel": os.getenv(
                "PLATFORM_BACKEND_RUN_DISPATCH_CHANNEL",
                cls._field_default("run_dispatch_channel"),
            ),
            "scheduler_poll_interval_seconds": int(
                os.getenv(
                    "PLATFORM_BACKEND_SCHEDULER_POLL_INTERVAL_SECONDS",
                    cls._field_default("scheduler_poll_interval_seconds"),
                )
            ),
            "state_db_path": os.getenv(
                "PLATFORM_BACKEND_STATE_DB_PATH",
                cls._field_default("state_db_path"),
            ),
        }
        raw_values["database_url"] = os.getenv("PLATFORM_BACKEND_DATABASE_URL", "")
        if not raw_values["database_url"] and os.getenv("MYSQL_HOST"):
            raw_values["database_url"] = URL.create(
                "mysql+pymysql",
                username=os.getenv("MYSQL_USER", "pyta"),
                password=os.getenv("MYSQL_PASSWORD", ""),
                host=os.environ["MYSQL_HOST"],
                port=int(os.getenv("MYSQL_PORT", "3306")),
                database=os.getenv("MYSQL_DATABASE", "pyta_platform"),
                query={"charset": "utf8mb4"},
            ).render_as_string(hide_password=False)
        raw_values["artifact_root"] = os.getenv("PLATFORM_BACKEND_ARTIFACT_ROOT", "")
        return cls(**raw_values)

    @staticmethod
    def _read_bool(raw_value: str, default: bool) -> bool:
        """把环境变量里的字符串转成布尔值。"""

        if raw_value is None:
            return default
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    def resolve_database_url(self) -> str:
        """生产/开发必须显式配置 MySQL；仅 test 环境允许离线数据库。"""
        if self.database_url:
            if make_url(self.database_url).drivername != "mysql+pymysql":
                raise ValueError("平台数据库必须使用 mysql+pymysql")
            return self.database_url
        if self.app_env != "test":
            raise ValueError("请配置 PLATFORM_BACKEND_DATABASE_URL 或 MYSQL_HOST 等 MySQL 参数")
        if not self.state_db_path:
            self.state_db_path = str(Path(gettempdir()) / ("pyta-test-" + uuid4().hex + ".sqlite3"))
        return self.state_db_path

    def resolve_state_db_path(self) -> str:
        """旧调用名的兼容入口；应用内部使用 resolve_database_url。"""
        return self.resolve_database_url()

    def resolve_artifact_root(self) -> Path:
        if self.artifact_root:
            return Path(self.artifact_root).expanduser().resolve()
        if self.app_env == "test":
            return Path(gettempdir()) / ("pyta-artifacts-" + uuid4().hex)
        return Path(".runtime/artifacts").resolve()

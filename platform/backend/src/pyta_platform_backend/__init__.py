"""应用导出延迟加载；迁移命令不需要先导入整套 HTTP/worker。"""

from pyta_platform_backend.config import BackendSettings

__all__ = ["BackendSettings", "create_app"]


def __getattr__(name):
    if name == "create_app":
        from pyta_platform_backend.app import create_app
        return create_app
    raise AttributeError(name)

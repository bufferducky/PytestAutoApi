"""Service exports load lazily so repository helpers do not import orchestration."""

from importlib import import_module

_EXPORTS = {
    "DemoSuiteService": "demo_suite_service",
    "ManagementService": "management_service",
    "RunService": "run_service",
    "WorkerControlService": "worker_control_service",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    globals()[name] = value
    return value

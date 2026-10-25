"""Retired demo API compatibility; no built-in product assets or execution."""

from fastapi import HTTPException

from pyta_platform_backend.schemas.demo_suite import ListDemoSuitesResponse


class DemoSuiteService:
    def __init__(self, run_service, management_repository=None):
        self._run_service = run_service

    def list_suites(self):
        return ListDemoSuitesResponse(items=[])

    def create_run_from_suite(self, suite_id, request):
        raise HTTPException(410, "demo_execution_disabled: 演示运行已移除，请使用真实版本化资产")

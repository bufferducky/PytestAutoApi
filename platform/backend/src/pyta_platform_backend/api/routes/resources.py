"""资源声明/账本与清理预检，不提供任意对象删除入口。"""

from fastapi import APIRouter


def create_resources_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["resources"])

    @router.get("/fixture-definitions")
    def definitions():
        return service.repository.definitions("fixtures")

    @router.post("/fixture-definitions", status_code=201)
    def define(payload: dict):
        return service.define(payload)

    @router.get("/resource-leases")
    def leases():
        return service.repository.pool()

    @router.post("/resource-pool", status_code=201)
    def pool(payload: dict):
        return service.add_pool(payload)

    @router.get("/runs/{run_id}/resources")
    def resources(run_id: str):
        service.runs.get_run_detail(run_id)
        return service.repository.resources(run_id)

    @router.post("/runs/{run_id}/cleanup-preflight")
    def cleanup_preflight(run_id: str):
        return service.cleanup_preflight(run_id)

    @router.post("/runs/{run_id}/cleanup")
    def cleanup(run_id: str, payload: dict):
        return service.cleanup(run_id, payload.get("preflight_token"))

    @router.post("/runs/{run_id}/resources/{resource_id}/reconciled")
    def reconciled(run_id: str, resource_id: str, payload: dict):
        return service.confirm_reconciled(run_id, resource_id, payload.get("reason"))

    @router.get("/media-datasets")
    def media():
        return service.repository.definitions("media")

    @router.post("/media-datasets", status_code=201)
    def add_media(payload: dict):
        return service.media(payload)

    @router.post("/media-datasets/{identifier}/versions/{version}/preflight")
    def media_preflight(identifier: str, version: int):
        return service.media_preflight(identifier, version)

    @router.post("/runs/{run_id}/resources/{resource_id}/renew")
    def renew(run_id: str, resource_id: str, payload: dict):
        return service.renew(resource_id, run_id, payload.get("seconds"))

    return router

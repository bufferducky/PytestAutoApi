"""真实计划与发布报告，旧目录迁移项默认暂停。"""

from fastapi import APIRouter, HTTPException

from pyta_platform_backend.schemas.schedules import ScheduleDefinition


def create_schedules_router(service, releases, prefix):
    router = APIRouter(prefix=prefix, tags=["schedules"])

    @router.get("/schedule-plans")
    def list_plans():
        return service.repository.schedules()

    @router.post("/schedules", status_code=201)
    def create(payload: ScheduleDefinition):
        return service.save(
            payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        )

    @router.patch("/schedules/{identifier}")
    def update(identifier: str, payload: dict):
        return service.save(payload["definition"], identifier, payload["expected_revision"])

    @router.delete("/schedules/{identifier}")
    def delete(identifier: str, revision: int):
        return service.change_status(identifier, revision, "deleted")

    @router.post("/schedules/{identifier}/pause")
    def pause(identifier: str, payload: dict):
        return service.change_status(identifier, payload["expected_revision"], "paused")

    @router.post("/schedules/{identifier}/resume")
    def resume(identifier: str, payload: dict):
        return service.change_status(identifier, payload["expected_revision"], "active")

    @router.get("/schedules/{identifier}/preview")
    def preview(identifier: str):
        return service.preview(identifier)

    @router.get("/schedules/{identifier}/triggers")
    def triggers(identifier: str):
        return service.repository.triggers(identifier)

    @router.get("/scheduler/status")
    def status():
        return service.status()

    @router.post("/scheduler/pause-all")
    def pause_all():
        return service.pause_all()

    @router.post("/release-reports", status_code=201)
    def release(payload: dict):
        return releases.build(payload)

    @router.get("/release-reports/{identifier}")
    def get_release(identifier: str):
        try:
            return releases.repository.get_report(identifier)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/notification-deliveries")
    def notification_deliveries():
        return service.repository.notification_deliveries()

    return router

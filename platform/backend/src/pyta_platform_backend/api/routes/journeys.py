from fastapi import APIRouter

from pyta_platform_backend.schemas.journeys import JourneyRunRequest


def create_journeys_router(service, prefix):
    router = APIRouter(prefix=prefix, tags=["journeys"])

    @router.get("/runner-capabilities")
    def capabilities():
        import importlib.util
        import shutil

        from pyta_platform_backend.runners.ui import web_runtime

        return {
            "web": web_runtime(),
            "android": {
                "appium_installed": importlib.util.find_spec("appium") is not None,
                "adb_available": shutil.which("adb") is not None,
            },
        }

    @router.get("/device-profiles")
    def devices():
        return service.repository.definitions("device-profile")

    @router.post("/device-profiles", status_code=201)
    def define_device(payload: dict):
        return service.device(payload)

    @router.post("/device-profiles/{identifier}/versions/{version}/preflight")
    def device_preflight(identifier: str, version: int):
        from pyta_platform_backend.runners.ui import device_preflight

        return device_preflight(service.get("device-profile", identifier, version)["data"])

    @router.get("/journeys")
    def journeys():
        return service.repository.definitions("journeys")

    @router.post("/journeys", status_code=201)
    def define(payload: dict):
        return service.define(payload)

    @router.post("/journeys/import-yanji-query", status_code=201)
    def import_yanji_query(payload: dict):
        from pyta_platform_backend.services.yanji_regression import import_web_query

        return import_web_query(service, payload)

    @router.post("/journeys/{identifier}/versions/{version}/preflight")
    def preflight(identifier: str, version: int):
        return service.preflight(identifier, version, True)

    @router.post("/journeys/{identifier}/versions/{version}/runs", status_code=202)
    def run(identifier: str, version: int, payload: JourneyRunRequest = None):
        return service.run(identifier, version, build=payload.build if payload else "unspecified")

    @router.post("/journeys/{identifier}/versions/{version}/quarantine", status_code=201)
    def quarantine(identifier: str, version: int, payload: dict):
        return service.quarantine(
            identifier, version, payload.get("reason"), payload.get("expires_at")
        )

    @router.get("/journey-readiness")
    def readiness(environment_id: str = None, build: str = None):
        return service.readiness(environment_id=environment_id, build=build)

    @router.post("/journey-quarantines/{identifier}/resolve", status_code=201)
    def resolve_quarantine(identifier: str, payload: dict):
        return service.resolve_quarantine(identifier, payload.get("reason"))

    return router
